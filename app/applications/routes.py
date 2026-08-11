import os

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_file, abort
from flask_login import login_required, current_user

from pypdf.errors import PdfReadError

import gmail_client
from app.extensions import db
from app.models import Job, Document, Application, GeneratedDocument, GeneratedEmail, ApplicationDocument
from app.applications.forms import CoverLetterForm, EmailForm, StatusForm
from app.applications.pdf_package import build_application_pdf, safe_package_filename
from app.ai.cover_letter import generate_cover_letter, validate_cover_letter
from app.ai.email_gen import generate_email
from app.ai.provider import AIProviderError
from app.documents.storage import LocalStorageProvider
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
    return render_template(
        "applications/detail.html",
        application=application,
        documents=documents,
        selected_ids=selected_ids,
        cover_letter_form=CoverLetterForm(obj=application.cover_letter),
        email_form=EmailForm(obj=application.email),
        status_form=StatusForm(obj=application),
    )


@bp.route("/<int:application_id>/generate-cover-letter", methods=["POST"])
@login_required
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

    storage = LocalStorageProvider(current_app.config["UPLOAD_DIR"])
    doc_paths = [
        (storage.full_path(sd.document.storage_path), sd.document.mime_type) for sd in application.selected_documents
    ]

    filename = safe_package_filename(
        current_user.profile.full_name if current_user.profile else current_user.email,
        application.job.company_name,
        application.job.title,
    )
    output_path = os.path.join(current_app.config["GENERATED_DIR"], str(current_user.id), filename)
    try:
        build_application_pdf(application.cover_letter.content, doc_paths, output_path)
    except (PdfReadError, OSError) as e:
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
    """Optional: creates a Gmail DRAFT (never sends) via gmail_client.py. Requires
    credentials.json to be configured (see README) - if it isn't, this fails
    gracefully and the user can still send manually using the downloaded package."""
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
        gmail_client.create_draft(
            application.contact_email,
            application.email.subject,
            application.email.body,
            application.package_storage_path,
        )
        application.log_event("gmail_draft_created", "Gmail draft created (not sent).")
        db.session.commit()
        flash("Gmail draft created - check your Drafts folder, review, and send it yourself.", "success")
    except FileNotFoundError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Could not create the Gmail draft: {e}", "error")
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
