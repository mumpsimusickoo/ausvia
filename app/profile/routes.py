from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models.profile import Education, Experience, Skill, Language, Preference
from app.profile.forms import (
    PersonalInfoForm,
    EducationForm,
    ExperienceForm,
    SkillForm,
    LanguageForm,
    PreferenceForm,
)

bp = Blueprint("profile", __name__, url_prefix="/profile")


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

    return render_template(
        "profile/view.html",
        profile=profile,
        personal_form=personal_form,
        preference_form=preference_form,
        education_form=EducationForm(),
        experience_form=ExperienceForm(),
        skill_form=SkillForm(),
        language_form=LanguageForm(),
    )


@bp.route("/personal", methods=["POST"])
@login_required
def update_personal():
    profile = _get_or_create_profile()
    form = PersonalInfoForm()
    if form.validate_on_submit():
        form.populate_obj(profile)
        db.session.commit()
        flash("Personal information updated.", "success")
    else:
        flash("Please correct the errors in the personal information form.", "error")
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
        flash("Preferences updated.", "success")
    else:
        flash("Please correct the errors in the preferences form.", "error")
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
        flash("Education entry added.", "success")
    else:
        flash("Please correct the errors in the education form.", "error")
    return redirect(url_for("profile.view"))


@bp.route("/education/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_education(entry_id):
    profile = _get_or_create_profile()
    entry = _owned_or_404(Education, entry_id, profile.id)
    db.session.delete(entry)
    db.session.commit()
    flash("Education entry removed.", "info")
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
        flash("Experience entry added.", "success")
    else:
        flash("Please correct the errors in the experience form.", "error")
    return redirect(url_for("profile.view"))


@bp.route("/experience/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_experience(entry_id):
    profile = _get_or_create_profile()
    entry = _owned_or_404(Experience, entry_id, profile.id)
    db.session.delete(entry)
    db.session.commit()
    flash("Experience entry removed.", "info")
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
        flash("Skill added.", "success")
    else:
        flash("Please correct the errors in the skill form.", "error")
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
        flash("Language added.", "success")
    else:
        flash("Please correct the errors in the language form.", "error")
    return redirect(url_for("profile.view"))


@bp.route("/language/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_language(entry_id):
    profile = _get_or_create_profile()
    entry = _owned_or_404(Language, entry_id, profile.id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for("profile.view"))
