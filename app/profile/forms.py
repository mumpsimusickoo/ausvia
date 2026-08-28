from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TextAreaField, SelectField, IntegerField, BooleanField
from wtforms.validators import Optional, Length, Email

from app.models.profile import CEFR_LEVELS, PROFICIENCY_LEVELS


def _max_length_message(max_len):
    return _l("Must be at most %(max)d characters long.", max=max_len)


def _optional_str(max_len=255):
    return [Optional(), Length(max=max_len, message=_max_length_message(max_len))]


NOT_SPECIFIED = _l("Not specified")


class PersonalInfoForm(FlaskForm):
    first_name = StringField(_l("First name"), validators=_optional_str())
    last_name = StringField(_l("Last name"), validators=_optional_str())
    date_of_birth = DateField(_l("Date of birth"), validators=[Optional()])
    nationality = StringField(_l("Nationality"), validators=_optional_str())
    address = StringField(_l("Address"), validators=_optional_str())
    city = StringField(_l("City"), validators=_optional_str())
    postal_code = StringField(_l("Postal code"), validators=[Optional(), Length(max=20, message=_max_length_message(20))])
    country = StringField(_l("Country"), validators=_optional_str())
    phone = StringField(_l("Phone"), validators=[Optional(), Length(max=50, message=_max_length_message(50))])
    contact_email = StringField(
        _l("Contact email"),
        validators=[Optional(), Email(message=_l("Please enter a valid email address.")), Length(max=255, message=_max_length_message(255))],
    )


class EducationForm(FlaskForm):
    institution = StringField(_l("Institution"), validators=[Length(min=1, max=255, message=_l("Must be between %(min)d and %(max)d characters long.", min=1, max=255))])
    degree = StringField(_l("Degree / diploma"), validators=_optional_str())
    field = StringField(_l("Field of study"), validators=_optional_str())
    start_date = DateField(_l("Start date"), validators=[Optional()])
    end_date = DateField(_l("End date"), validators=[Optional()])
    country = StringField(_l("Country"), validators=_optional_str())
    description = TextAreaField(_l("Description"), validators=[Optional(), Length(max=2000, message=_max_length_message(2000))])


class ExperienceForm(FlaskForm):
    company = StringField(_l("Company"), validators=[Length(min=1, max=255, message=_l("Must be between %(min)d and %(max)d characters long.", min=1, max=255))])
    role = StringField(_l("Role"), validators=_optional_str())
    start_date = DateField(_l("Start date"), validators=[Optional()])
    end_date = DateField(_l("End date"), validators=[Optional()])
    responsibilities = TextAreaField(_l("Responsibilities"), validators=[Optional(), Length(max=2000, message=_max_length_message(2000))])
    achievements = TextAreaField(_l("Achievements"), validators=[Optional(), Length(max=2000, message=_max_length_message(2000))])


class SkillForm(FlaskForm):
    name = StringField(_l("Skill"), validators=[Length(min=1, max=120, message=_l("Must be between %(min)d and %(max)d characters long.", min=1, max=120))])
    proficiency = SelectField(
        _l("Proficiency"),
        choices=lambda: [("", NOT_SPECIFIED)] + [(p, p.capitalize()) for p in PROFICIENCY_LEVELS],
        validators=[Optional()],
    )


class LanguageForm(FlaskForm):
    name = StringField(_l("Language"), validators=[Length(min=1, max=100, message=_l("Must be between %(min)d and %(max)d characters long.", min=1, max=100))])
    level = SelectField(
        _l("Level"), choices=lambda: [("", NOT_SPECIFIED)] + [(lvl, lvl) for lvl in CEFR_LEVELS], validators=[Optional()]
    )


class PreferenceForm(FlaskForm):
    fields = StringField(_l("Ausbildung fields (comma-separated)"), validators=[Optional(), Length(max=1000, message=_max_length_message(1000))])
    locations = StringField(
        _l("Preferred locations (comma-separated, blank = Germany-wide)"),
        validators=[Optional(), Length(max=1000, message=_max_length_message(1000))],
    )
    desired_start_date = StringField(_l("Desired start date"), validators=[Optional(), Length(max=20, message=_max_length_message(20))])
    min_german_level = SelectField(
        _l("Minimum German level"),
        choices=lambda: [("", NOT_SPECIFIED)] + [(lvl, lvl) for lvl in CEFR_LEVELS],
        validators=[Optional()],
    )
    max_distance_km = IntegerField(_l("Max distance (km)"), validators=[Optional()])
    open_to_relocation = BooleanField(_l("Open to relocation"))
    other_notes = TextAreaField(_l("Other preferences"), validators=[Optional(), Length(max=2000, message=_max_length_message(2000))])
