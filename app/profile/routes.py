import io
from datetime import date

from flask import Blueprint, render_template, redirect, url_for, flash, send_file
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_babel import ngettext
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.models.document import Document
from app.models.profile import Education, Experience, Skill, Language, Preference
from app.profile.forms import (
    PersonalInfoForm,
    EducationForm,
    ExperienceForm,
    SkillForm,
    LanguageForm,
    PreferenceForm,
)
from app.models.ai import PROCESS_QA_QUESTIONS
from app.ai.provider import AIProviderError
from app.ai.profile_coaching import get_profile_coaching, generate_profile_coaching
from app.ai.process_qa import get_process_qa_answer, generate_process_qa_answer
from app.profile.cv_export import build_cv_pdf, safe_cv_filename
from app.utils.logging import log_event

bp = Blueprint("profile", __name__, url_prefix="/profile")


def _age(date_of_birth):
    if not date_of_birth:
        return None
    today = date.today()
    years = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return years


# Screens pass 5 (Profile, 2026-08-28): the bundle's own completeness
# panel is four real done-or-missing sentences ("Personendaten
# vollständig" / "Sprachzertifikat nicht hochgeladen"), not a bare label
# list - this pairs CandidateProfile.completeness_checklist()'s eight
# generic (label, satisfied) checks (reused as-is, per the task - not a
# second completeness calculation) with a done/missing phrasing for each,
# rather than the Dashboard pass's single summary sentence (a deliberate
# simplification for that screen's compact rail card, not a general
# checklist component - see DECISIONS.md).
_COMPLETENESS_PHRASING = {
    "Name": (_l("Name provided"), _l("Name missing")),
    "Location": (_l("Location provided"), _l("Location missing")),
    "Phone number": (_l("Phone number provided"), _l("Phone number missing")),
    "Contact email": (_l("Contact email provided"), _l("Contact email missing")),
    "Education": (_l("Education entries added"), _l("No education entries yet")),
    "Skills": (_l("Skills added"), _l("No skills added yet")),
    "Languages": (_l("Languages added"), _l("No languages added yet")),
    "Job preferences": (_l("Ausbildung preferences set"), _l("Ausbildung preferences not set")),
}


def _completeness_lines(checklist):
    return [
        (_COMPLETENESS_PHRASING.get(label, (label, label))[0 if ok else 1], ok)
        for label, ok in checklist
    ]


def _language_proof_note(language, has_german_certificate):
    """Screens pass 5 (Profile, 2026-08-28): the bundle shows a proof-state
    caption per language ("Goethe-Zertifikat vorhanden" / "Schulkenntnisse,
    kein Nachweis"), but this schema only tracks certificate evidence for
    German specifically (Document.is_primary_german_cert - there's no
    is_primary_english_cert or similar for any other language). Rather than
    claim "no evidence" for a language this app has no way to actually
    check, the proof caption is German-only; every other non-native
    language just shows its level, honestly not extended past what's
    real - see DECISIONS.md.

    Returns (text, is_warning) - i18n pass 2: profile/view.html used to
    decide the warning color by checking "no certificate" in note.lower(),
    which only ever worked because that substring happened to still be
    English. Once `text` became a real translated string, that check would
    silently stop matching in German. `is_warning` is a stable, never-
    translated signal instead - same "code vs. display text" split as
    APPLICATION_STATUS_LABELS/reason_codes elsewhere in this pass."""
    if language.level == "Native":
        return _("Native language"), False
    if language.name.strip().lower() == "german":
        if has_german_certificate:
            return _("Certificate on file"), False
        return _("School-level, no certificate on file"), True
    return None, False


def _get_or_create_profile():
    profile = current_user.profile
    if profile is None:
        from app.models import CandidateProfile

        profile = CandidateProfile(user_id=current_user.id, contact_email=current_user.email)
        db.session.add(profile)
        db.session.commit()
    return profile


def _owned_or_404(model, entry_id, profile_id):
    entry = db.get_or_404(model, entry_id)
    if entry.profile_id != profile_id:
        # Never let a user reach another user's profile sub-entity by guessing an ID.
        from flask import abort

        abort(404)
    return entry


@bp.route("/", methods=["GET"])
@login_required
def view():
    profile = _get_or_create_profile()
    personal_form = PersonalInfoForm(obj=profile)
    if profile.preference:
        preference_form = PreferenceForm(
            fields=", ".join(profile.preference.fields or []),
            locations=", ".join(profile.preference.locations or []),
            desired_start_date=profile.preference.desired_start_date,
            min_german_level=profile.preference.min_german_level,
            max_distance_km=profile.preference.max_distance_km,
            open_to_relocation=profile.preference.open_to_relocation,
            other_notes=profile.preference.other_notes,
        )
    else:
        preference_form = PreferenceForm(open_to_relocation=True)

    age = _age(profile.date_of_birth)
    meta_parts = [
        ngettext("%(num)d year old", "%(num)d years old", age) if age is not None else None,
        profile.nationality,
        profile.city,
        profile.contact_email,
    ]
    profile_meta_line = " · ".join(p for p in meta_parts if p)

    has_german_certificate = Document.query.filter_by(
        user_id=current_user.id, is_primary_german_cert=True
    ).first() is not None
    language_notes = {lang.id: _language_proof_note(lang, has_german_certificate) for lang in profile.languages}

    pref = profile.preference
    preference_lines = [
        (_("Fields"), ", ".join(pref.fields) if pref and pref.fields else _("Any")),
        (_("Locations"), ", ".join(pref.locations) if pref and pref.locations else _("Germany-wide")),
        (_("Relocation"), (_("Open to it") if pref.open_to_relocation else _("Not open to it")) if pref else _("Not set")),
        (_("Min. German level"), pref.min_german_level if pref and pref.min_german_level else _("Not set")),
        (_("Desired start"), pref.desired_start_date if pref and pref.desired_start_date else _("Not set")),
    ]

    return render_template(
        "profile/view.html",
        profile=profile,
        age=age,
        profile_meta_line=profile_meta_line,
        avatar_initials="".join(p[0] for p in (profile.first_name, profile.last_name) if p).upper() or "?",
        completeness=profile.completeness_percent(),
        completeness_lines=_completeness_lines(profile.completeness_checklist()),
        language_notes=language_notes,
        preference_lines=preference_lines,
        personal_form=personal_form,
        preference_form=preference_form,
        education_form=EducationForm(),
        experience_form=ExperienceForm(),
        skill_form=SkillForm(),
        language_form=LanguageForm(),
        coaching=get_profile_coaching(current_user),
        qa_questions=PROCESS_QA_QUESTIONS,
        qa_answers={key: get_process_qa_answer(current_user, key) for key in PROCESS_QA_QUESTIONS},
    )


@bp.route("/cv.pdf", methods=["GET"])
@login_required
def download_cv():
    """Real, deterministic PDF export of the candidate's own profile data
    (design-audit decision, 2026-08-24) - no AI call, see
    app/profile/cv_export.py's module docstring."""
    profile = _get_or_create_profile()
    pdf_bytes = build_cv_pdf(profile)
    return send_file(
        io.BytesIO(pdf_bytes),
        download_name=safe_cv_filename(profile.full_name),
        as_attachment=True,
        mimetype="application/pdf",
    )


@bp.route("/coaching", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_coaching():
    try:
        generate_profile_coaching(current_user)
        flash(_("Profile review generated."), "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Profile coaching generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("profile.view"))


@bp.route("/qa/<question_key>", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_qa_answer(question_key):
    if question_key not in PROCESS_QA_QUESTIONS:
        from flask import abort

        abort(404)
    try:
        generate_process_qa_answer(current_user, question_key)
        flash(_("Answer generated."), "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Process Q&A generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("profile.view"))


@bp.route("/personal", methods=["POST"])
@login_required
def update_personal():
    profile = _get_or_create_profile()
    form = PersonalInfoForm()
    if form.validate_on_submit():
        form.populate_obj(profile)
        db.session.commit()
        flash(_("Personal information updated."), "success")
    else:
        flash(_("Please correct the errors in the personal information form."), "error")
    return redirect(url_for("profile.view"))


@bp.route("/preferences", methods=["POST"])
@login_required
def update_preferences():
    profile = _get_or_create_profile()
    form = PreferenceForm()
    if form.validate_on_submit():
        pref = profile.preference or Preference(profile_id=profile.id)
        pref.fields = [f.strip() for f in form.fields.data.split(",") if f.strip()]
        pref.locations = [l.strip() for l in form.locations.data.split(",") if l.strip()]
        pref.desired_start_date = form.desired_start_date.data or None
        pref.min_german_level = form.min_german_level.data or None
        pref.max_distance_km = form.max_distance_km.data
        pref.open_to_relocation = form.open_to_relocation.data
        pref.other_notes = form.other_notes.data
        if pref.id is None:
            db.session.add(pref)
        db.session.commit()
        flash(_("Preferences updated."), "success")
    else:
        flash(_("Please correct the errors in the preferences form."), "error")
    return redirect(url_for("profile.view"))


@bp.route("/education/add", methods=["POST"])
@login_required
def add_education():
    profile = _get_or_create_profile()
    form = EducationForm()
    if form.validate_on_submit():
        entry = Education(profile_id=profile.id)
        form.populate_obj(entry)
        db.session.add(entry)
        db.session.commit()
        flash(_("Education entry added."), "success")
    else:
        flash(_("Please correct the errors in the education form."), "error")
    return redirect(url_for("profile.view"))


@bp.route("/education/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_education(entry_id):
    profile = _get_or_create_profile()
    entry = _owned_or_404(Education, entry_id, profile.id)
    db.session.delete(entry)
    db.session.commit()
    flash(_("Education entry removed."), "info")
    return redirect(url_for("profile.view"))


@bp.route("/experience/add", methods=["POST"])
@login_required
def add_experience():
    profile = _get_or_create_profile()
    form = ExperienceForm()
    if form.validate_on_submit():
        entry = Experience(profile_id=profile.id)
        form.populate_obj(entry)
        db.session.add(entry)
        db.session.commit()
        flash(_("Experience entry added."), "success")
    else:
        flash(_("Please correct the errors in the experience form."), "error")
    return redirect(url_for("profile.view"))


@bp.route("/experience/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_experience(entry_id):
    profile = _get_or_create_profile()
    entry = _owned_or_404(Experience, entry_id, profile.id)
    db.session.delete(entry)
    db.session.commit()
    flash(_("Experience entry removed."), "info")
    return redirect(url_for("profile.view"))


@bp.route("/skill/add", methods=["POST"])
@login_required
def add_skill():
    profile = _get_or_create_profile()
    form = SkillForm()
    if form.validate_on_submit():
        entry = Skill(profile_id=profile.id, name=form.name.data, proficiency=form.proficiency.data or None)
        db.session.add(entry)
        db.session.commit()
        flash(_("Skill added."), "success")
    else:
        flash(_("Please correct the errors in the skill form."), "error")
    return redirect(url_for("profile.view"))


@bp.route("/skill/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_skill(entry_id):
    profile = _get_or_create_profile()
    entry = _owned_or_404(Skill, entry_id, profile.id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for("profile.view"))


@bp.route("/language/add", methods=["POST"])
@login_required
def add_language():
    profile = _get_or_create_profile()
    form = LanguageForm()
    if form.validate_on_submit():
        entry = Language(profile_id=profile.id, name=form.name.data, level=form.level.data or None)
        db.session.add(entry)
        db.session.commit()
        flash(_("Language added."), "success")
    else:
        flash(_("Please correct the errors in the language form."), "error")
    return redirect(url_for("profile.view"))


@bp.route("/language/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_language(entry_id):
    profile = _get_or_create_profile()
    entry = _owned_or_404(Language, entry_id, profile.id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for("profile.view"))
