import os

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_file, abort
from flask_login import login_required, current_user

from pypdf.errors import PdfReadError

from app.extensions import db, limiter
from app.models import Job, Document, Application, GeneratedDocument, GeneratedEmail, FollowUpEmail, ApplicationDocument
from app.models.integration import GmailMessage
from app.models.task import BackgroundTask
from app.applications.forms import CoverLetterForm, EmailForm, FollowUpEmailForm, StatusForm
from app.applications.pdf_package import build_application_pdf, safe_package_filename
from app.applications.status_route import build_status_route
from app.ai.cover_letter import generate_cover_letter, validate_cover_letter
from app.ai.cv_profile_statement import get_cv_profile_statement, generate_cv_profile_statement
from app.ai.email_gen import generate_email
from app.ai.followup_email import generate_followup_email
from app.ai.interview_prep import get_interview_prep, generate_interview_prep
from app.ai.provider import AIProviderError
from app.ai.reply_ai import classify_reply, generate_reply_suggestion
from app.documents.storage import get_storage_provider
from app.integrations import gmail_oauth, gmail_drafts
from app.integrations.gmail_reply_tracking import check_for_replies
from app.jobs.matching import get_or_compute_match
from app.tasks.runner import submit_task
from app.utils.logging import log_event

bp = Blueprint("applications", __name__, url_prefix="/applications")

DOC_TYPE_LABEL_DE = {
    "cv": "Lebenslauf",
    "diploma": "Zeugnis/Diplom",
    "language_certificate": "Sprachzertifikat",
    "training_certificate": "Ausbildungszertifikat",
    "transcript": "Notenübersicht",
    "recommendation_letter": "Empfehlungsschreiben",
    "other": "weitere Unterlagen",
}

# suggested default package order (spec section 23): CV, then diploma/certs, then the rest
DOC_TYPE_ORDER = ["cv", "diploma", "language_certificate", "training_certificate", "transcript", "recommendation_letter", "other"]

# Application deletion: statuses where nothing has left AUSVIA yet - no
# email has actually been sent (that's still a manual, user-driven action
# even at "ready", which just means the package is built), no interview
# has happened, nothing to lose but draft work. Deleting one of these
# needs only the normal single confirm(). Anything past this point
# represents something that actually happened in the real world - a
# real correspondence timeline, dates, notes - and needs a typed
# confirmation, enforced server-side, not just a JS dialog someone could
# click through without reading.
LOW_RISK_DELETE_STATUSES = ("preparing", "ready")
DELETE_CONFIRMATION_PHRASE = "DELETE"


def _owned_application_or_404(application_id):
    application = db.get_or_404(Application, application_id)
    if application.user_id != current_user.id:
        abort(404)
    return application


@bp.route("/")
@login_required
def list_applications():
    applications = (
        Application.query.filter_by(user_id=current_user.id).order_by(Application.updated_at.desc()).all()
    )
    return render_template("applications/list.html", applications=applications)


@bp.route("/start/<int:job_id>", methods=["POST"])
@login_required
def start(job_id):
    job = db.get_or_404(Job, job_id)
    application = Application.query.filter_by(user_id=current_user.id, job_id=job.id).first()
    if not application:
        application = Application(
            user_id=current_user.id,
            job_id=job.id,
            contact_person=job.contact_person,
            contact_email=job.contact_email,
            application_url=job.preferred_application_url,
        )
        db.session.add(application)
        db.session.flush()
        application.log_event("created", "Application started.")
        db.session.commit()
        log_event("application", "Application started.", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>")
@login_required
def detail(application_id):
    application = _owned_application_or_404(application_id)
    documents = Document.query.filter_by(user_id=current_user.id).order_by(Document.uploaded_at.desc()).all()
    selected_ids = {sd.document_id for sd in application.selected_documents}
    gmail_messages = (
        GmailMessage.query.filter_by(application_id=application.id)
        .order_by(GmailMessage.created_at.desc())
        .all()
    )
    # Phase 6: reply-checking now runs as a background task (see
    # app/tasks/runner.py) so this page never blocks on the Gmail API - show
    # whatever the most recent check for *this* application is doing/did.
    # BackgroundTask.context is a plain JSON dict, filtered in Python rather
    # than at the DB layer since SQLite JSON querying isn't worth the
    # portability tradeoff for "last 5 rows of one user's one task type."
    reply_check_task = next(
        (
            t for t in BackgroundTask.query
            .filter_by(user_id=current_user.id, task_type="gmail_check_replies")
            .order_by(BackgroundTask.created_at.desc())
            .limit(5)
            if t.context and t.context.get("application_id") == application.id
        ),
        None,
    )
    return render_template(
        "applications/detail.html",
        application=application,
        documents=documents,
        selected_ids=selected_ids,
        gmail_messages=gmail_messages,
        gmail_connected=gmail_oauth.get_connection(current_user) is not None,
        reply_check_task=reply_check_task,
        cover_letter_form=CoverLetterForm(obj=application.cover_letter),
        email_form=EmailForm(obj=application.email),
        followup_email_form=FollowUpEmailForm(obj=application.follow_up_email),
        status_form=StatusForm(obj=application),
        status_route=build_status_route(application),
        interview_prep=get_interview_prep(application),
        cv_profile_statement=get_cv_profile_statement(application),
        # Deterministic, already-computed elsewhere (no new AI call, no new
        # model) - reused here to surface real matched strengths alongside
        # the CV profile statement, per the CV-tailoring investigation.
        match=get_or_compute_match(current_user, application.job),
    )


@bp.route("/<int:application_id>/generate-cover-letter", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_cover_letter_route(application_id):
    application = _owned_application_or_404(application_id)
    try:
        text, source, provider = generate_cover_letter(current_user, application.job)
        validated, notes, corrected = validate_cover_letter(current_user, application.job, text, source)
        final_text = corrected or text

        letter = application.cover_letter or GeneratedDocument(application_id=application.id)
        letter.content = final_text
        letter.source = source
        letter.provider = provider
        letter.validated = validated
        letter.validation_notes = notes
        if letter.id is None:
            db.session.add(letter)
        application.log_event("cover_letter_generated", f"Cover letter generated ({source}).")
        db.session.commit()
        flash("Cover letter generated.", "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Cover letter generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/cover-letter", methods=["POST"])
@login_required
def save_cover_letter(application_id):
    application = _owned_application_or_404(application_id)
    form = CoverLetterForm()
    if form.validate_on_submit():
        letter = application.cover_letter or GeneratedDocument(application_id=application.id, source="manual")
        letter.content = form.content.data
        if letter.id is None:
            db.session.add(letter)
        else:
            from app.models.user import utcnow

            letter.edited_at = utcnow()
        application.log_event("cover_letter_edited", "Cover letter edited manually.")
        db.session.commit()
        flash("Cover letter saved.", "success")
    else:
        flash("Please enter cover letter text.", "error")
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/generate-email", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_email_route(application_id):
    application = _owned_application_or_404(application_id)
    selected_types = [sd.document.doc_type for sd in application.selected_documents]
    summary = ", ".join(DOC_TYPE_LABEL_DE.get(t, t) for t in dict.fromkeys(selected_types)) or "Lebenslauf und Zeugnisse"

    try:
        subject, body, source, provider = generate_email(current_user, application.job, summary)
        email = application.email or GeneratedEmail(application_id=application.id)
        email.subject, email.body, email.source, email.provider = subject, body, source, provider
        if email.id is None:
            db.session.add(email)
        application.log_event("email_generated", f"Application email generated ({source}).")
        db.session.commit()
        flash("Email generated.", "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Email generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/email", methods=["POST"])
@login_required
def save_email(application_id):
    application = _owned_application_or_404(application_id)
    form = EmailForm()
    if form.validate_on_submit():
        email = application.email or GeneratedEmail(application_id=application.id, source="manual")
        email.subject, email.body = form.subject.data, form.body.data
        if email.id is None:
            db.session.add(email)
        else:
            from app.models.user import utcnow

            email.edited_at = utcnow()
        application.log_event("email_edited", "Email edited manually.")
        db.session.commit()
        flash("Email saved.", "success")
    else:
        flash("Please fill in subject and body.", "error")
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/generate-followup-email", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_followup_email_route(application_id):
    application = _owned_application_or_404(application_id)
    if application.status not in ("sent", "follow_up"):
        flash("Follow-up emails are only available once an application has been sent.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))

    try:
        subject, body, source, provider = generate_followup_email(current_user, application)
        followup = application.follow_up_email or FollowUpEmail(application_id=application.id)
        followup.subject, followup.body, followup.source, followup.provider = subject, body, source, provider
        if followup.id is None:
            db.session.add(followup)
        application.log_event("followup_email_generated", f"Follow-up email generated ({source}).")
        db.session.commit()
        flash("Follow-up email drafted.", "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Follow-up email generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/followup-email", methods=["POST"])
@login_required
def save_followup_email(application_id):
    application = _owned_application_or_404(application_id)
    form = FollowUpEmailForm()
    if form.validate_on_submit():
        followup = application.follow_up_email or FollowUpEmail(application_id=application.id, source="manual")
        followup.subject, followup.body = form.subject.data, form.body.data
        if followup.id is None:
            db.session.add(followup)
        else:
            from app.models.user import utcnow

            followup.edited_at = utcnow()
        application.log_event("followup_email_edited", "Follow-up email edited manually.")
        db.session.commit()
        flash("Follow-up email saved.", "success")
    else:
        flash("Please fill in subject and body.", "error")
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/interview-prep", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_interview_prep_route(application_id):
    application = _owned_application_or_404(application_id)
    try:
        generate_interview_prep(current_user, application)
        flash("Interview prep generated.", "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Interview prep generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/cv-profile-statement", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_cv_profile_statement_route(application_id):
    application = _owned_application_or_404(application_id)
    try:
        generate_cv_profile_statement(current_user, application)
        flash("CV profile statement generated.", "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"CV profile statement generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/documents", methods=["POST"])
@login_required
def select_documents(application_id):
    application = _owned_application_or_404(application_id)
    selected_ids = [int(v) for v in request.form.getlist("document_ids")]

    owned_docs = {
        d.id: d for d in Document.query.filter(Document.user_id == current_user.id, Document.id.in_(selected_ids)).all()
    } if selected_ids else {}

    ApplicationDocument.query.filter_by(application_id=application.id).delete()
    ordered = sorted(owned_docs.values(), key=lambda d: DOC_TYPE_ORDER.index(d.doc_type) if d.doc_type in DOC_TYPE_ORDER else len(DOC_TYPE_ORDER))
    for index, doc in enumerate(ordered):
        db.session.add(ApplicationDocument(application_id=application.id, document_id=doc.id, order_index=index))

    application.log_event("documents_selected", f"{len(ordered)} document(s) selected for the package.")
    db.session.commit()
    flash("Document selection saved.", "success")
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/approve", methods=["POST"])
@login_required
def approve(application_id):
    application = _owned_application_or_404(application_id)

    if not application.cover_letter or not application.cover_letter.content:
        flash("Generate or write a cover letter before approving.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))
    if not application.selected_documents:
        flash("Select at least one document to include before approving.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))

    storage = get_storage_provider(current_app.config)
    filename = safe_package_filename(
        current_user.profile.full_name if current_user.profile else current_user.email,
        application.job.company_name,
        application.job.title,
    )
    output_path = os.path.join(current_app.config["GENERATED_DIR"], str(current_user.id), filename)
    try:
        doc_paths = [
            (storage.full_path(sd.document.storage_path), sd.document.mime_type)
            for sd in application.selected_documents
        ]
        build_application_pdf(application.cover_letter.content, doc_paths, output_path)
    except (PdfReadError, OSError) as e:  # FileNotFoundError is an OSError subclass
        flash(
            "Could not build the package - one of the selected documents appears to be "
            "corrupted or unreadable. Please re-upload it and try again.",
            "error",
        )
        log_event("application", f"PDF package build failed: {e}", level="error", user_id=current_user.id)
        return redirect(url_for("applications.detail", application_id=application.id))

    application.package_storage_path = output_path
    application.package_filename = filename
    application.status = "ready"
    application.log_event("approved", "Application approved by user - package generated.")
    db.session.commit()
    log_event("application", "Application approved and package built.", user_id=current_user.id)
    flash("Application approved. Package ready to download.", "success")
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/download")
@login_required
def download_package(application_id):
    application = _owned_application_or_404(application_id)
    if not application.package_storage_path or not os.path.exists(application.package_storage_path):
        abort(404)
    return send_file(application.package_storage_path, download_name=application.package_filename, as_attachment=True)


@bp.route("/<int:application_id>/mark-sent", methods=["POST"])
@login_required
def mark_sent(application_id):
    application = _owned_application_or_404(application_id)
    if application.status != "ready":
        flash("Approve the application (generate the package) before marking it sent.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))

    from app.models.user import utcnow

    application.status = "sent"
    application.sent_at = utcnow()
    application.log_event("sent", "Marked as sent by user.")
    db.session.commit()
    flash("Marked as sent.", "success")
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/gmail-draft", methods=["POST"])
@login_required
def create_gmail_draft(application_id):
    """Creates a Gmail DRAFT (never sends) using the current user's own
    connected Gmail account (app/integrations/gmail_oauth.py) - not a single
    shared credential. Requires the user to have connected Gmail first."""
    application = _owned_application_or_404(application_id)
    if application.status != "ready" or not application.package_storage_path:
        flash("Approve the application first to build the package.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))
    if not application.email:
        flash("Generate or write an application email first.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))
    if not application.contact_email:
        flash("Add a contact email for this application first.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))

    try:
        service = gmail_oauth.get_gmail_service(current_user)
        gmail_drafts.create_draft(
            service,
            application.contact_email,
            application.email.subject,
            application.email.body,
            application.package_storage_path,
        )
        application.log_event("gmail_draft_created", "Gmail draft created (not sent).")
        db.session.commit()
        flash("Gmail draft created - check your Drafts folder, review, and send it yourself.", "success")
    except gmail_oauth.GmailNotConnectedError:
        flash("Connect your Gmail account first.", "error")
    except gmail_oauth.GmailNotConfiguredError as e:
        flash(str(e), "error")
    except Exception as e:
        # Phase 8 security audit (2.6): was flashing str(e) - the same class
        # of bug W3 fixed for background-task errors, in a spot that fix
        # didn't reach. Raw detail stays server-side in the log only.
        flash("Could not create the Gmail draft. Please try again.", "error")
        log_event("email", f"Gmail draft creation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/status", methods=["POST"])
@login_required
def update_status(application_id):
    application = _owned_application_or_404(application_id)
    form = StatusForm()
    if form.validate_on_submit():
        old_status = application.status
        form.populate_obj(application)
        db.session.commit()
        if old_status != application.status:
            application.log_event("status_changed", f"Status changed: {old_status} -> {application.status}.")
            db.session.commit()
        flash("Application updated.", "success")
    else:
        flash("Please correct the errors in the form.", "error")
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/delete", methods=["POST"])
@login_required
def delete(application_id):
    application = _owned_application_or_404(application_id)

    if application.status not in LOW_RISK_DELETE_STATUSES:
        # Real, server-side enforcement - not just a JS confirm() someone
        # could bypass with a direct POST. Checked case-insensitively so a
        # stray Caps Lock doesn't block a genuine attempt.
        typed = (request.form.get("confirm_text") or "").strip().upper()
        if typed != DELETE_CONFIRMATION_PHRASE:
            flash(
                f'This application is past "preparing" and represents real history - '
                f'type {DELETE_CONFIRMATION_PHRASE} to confirm permanent deletion.',
                "error",
            )
            return redirect(url_for("applications.detail", application_id=application.id))

    # Generated PDF packages were deliberately kept local-disk-only, not
    # routed through the storage abstraction (see DEPLOYMENT.md's "Known
    # gaps") - clean up the file directly rather than leaving it orphaned
    # on disk. Missing/already-gone is not an error.
    if application.package_storage_path and os.path.exists(application.package_storage_path):
        try:
            os.remove(application.package_storage_path)
        except OSError as e:
            log_event(
                "application", f"Could not remove package file on delete: {e}",
                level="warning", user_id=current_user.id,
            )

    # JobMatch is deliberately NOT touched here - it's keyed by (user_id,
    # job_id), not application_id, and represents the candidate's fit
    # against the job itself, independent of whether/how they applied. It
    # should survive this application being deleted (e.g. the user may
    # reapply, or just still want to see their match score in search
    # results) - cascading its deletion here would be deleting real,
    # unrelated data.
    job_title = application.job.title
    db.session.delete(application)
    db.session.commit()
    log_event("application", f"Application deleted ({job_title}).", user_id=current_user.id)
    flash("Application deleted.", "info")
    return redirect(url_for("applications.list_applications"))


def _owned_message_or_404(application, message_id):
    message = db.get_or_404(GmailMessage, message_id)
    if message.application_id != application.id:
        abort(404)
    return message


@bp.route("/<int:application_id>/check-replies", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def check_replies(application_id):
    """Manual, user-triggered check (spec: reply tracking) - runs as a
    background task (Phase 6, see app/tasks/runner.py) rather than blocking
    this request on the Gmail API call, since that's exactly the kind of
    slow network operation background jobs exist for. Searches the
    connected Gmail inbox for messages from this application's contact
    email; cannot track an exact thread from the start since AUSVIA never
    sends the original email itself."""
    application = _owned_application_or_404(application_id)

    if not gmail_oauth.get_connection(current_user):
        flash("Connect your Gmail account first.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))
    if not application.contact_email:
        flash("Add a contact email above to check for replies.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))

    submit_task(
        current_user,
        "gmail_check_replies",
        _run_check_replies,
        current_user.id,
        application.id,
        context={"application_id": application.id},
    )
    flash("Checking for replies in the background - refresh in a few seconds to see results.", "info")
    return redirect(url_for("applications.detail", application_id=application.id))


def _run_check_replies(user_id, application_id):
    """Runs on a background-task worker thread (its own app/db context, no
    request) - re-fetches user/application by ID rather than closing over
    the request-scoped objects, since those belong to a session that's
    already gone by the time this runs."""
    from app.models import User

    user = db.session.get(User, user_id)
    application = db.session.get(Application, application_id)
    service = gmail_oauth.get_gmail_service(user)
    new_messages = check_for_replies(user, application, service)
    return f"{len(new_messages)} new message(s) found." if new_messages else "No new messages found."


@bp.route("/<int:application_id>/messages/<int:message_id>/classify", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def classify_message(application_id, message_id):
    application = _owned_application_or_404(application_id)
    message = _owned_message_or_404(application, message_id)
    classify_reply(current_user, application, message)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/messages/<int:message_id>/suggest-reply", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def suggest_reply(application_id, message_id):
    application = _owned_application_or_404(application_id)
    message = _owned_message_or_404(application, message_id)
    try:
        generate_reply_suggestion(current_user, application, message)
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Reply suggestion failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))


@bp.route("/<int:application_id>/messages/<int:message_id>/create-reply-draft", methods=["POST"])
@login_required
def create_reply_draft(application_id, message_id):
    application = _owned_application_or_404(application_id)
    message = _owned_message_or_404(application, message_id)

    reply_text = (request.form.get("reply_text") or message.ai_suggested_reply or "").strip()
    if not reply_text:
        flash("Write or generate a reply first.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))
    if not message.from_address:
        flash("This message has no sender address on file.", "error")
        return redirect(url_for("applications.detail", application_id=application.id))

    try:
        service = gmail_oauth.get_gmail_service(current_user)
        gmail_drafts.create_reply_draft(
            service,
            message.from_address,
            message.subject or f"Re: {application.job.title}",
            reply_text,
            thread_id=message.gmail_thread_id,
            in_reply_to_rfc_id=message.rfc_message_id,
        )
        application.log_event("reply_draft_created", "Reply draft created (not sent).")
        db.session.commit()
        flash("Reply draft created in Gmail - review and send it yourself.", "success")
    except gmail_oauth.GmailNotConnectedError:
        flash("Connect your Gmail account first.", "error")
    except Exception as e:
        # Phase 8 security audit (2.6): same reasoning as create_gmail_draft
        # above - raw detail stays server-side in the log only.
        flash("Could not create the reply draft. Please try again.", "error")
        log_event("gmail", f"Reply draft creation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("applications.detail", application_id=application.id))
