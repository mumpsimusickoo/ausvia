from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TextAreaField, SelectField, IntegerField, BooleanField
from wtforms.validators import Optional, Length, Email

from app.models.profile import CEFR_LEVELS, PROFICIENCY_LEVELS

OPTIONAL_STR = [Optional(), Length(max=255)]


class PersonalInfoForm(FlaskForm):
    first_name = StringField("First name", validators=OPTIONAL_STR)
    last_name = StringField("Last name", validators=OPTIONAL_STR)
    date_of_birth = DateField("Date of birth", validators=[Optional()])
    nationality = StringField("Nationality", validators=OPTIONAL_STR)
    address = StringField("Address", validators=OPTIONAL_STR)
    city = StringField("City", validators=OPTIONAL_STR)
    postal_code = StringField("Postal code", validators=[Optional(), Length(max=20)])
    country = StringField("Country", validators=OPTIONAL_STR)
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    contact_email = StringField("Contact email", validators=[Optional(), Email(), Length(max=255)])


class EducationForm(FlaskForm):
    institution = StringField("Institution", validators=[Length(min=1, max=255)])
    degree = StringField("Degree / diploma", validators=OPTIONAL_STR)
    field = StringField("Field of study", validators=OPTIONAL_STR)
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])
    country = StringField("Country", validators=OPTIONAL_STR)
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])


class ExperienceForm(FlaskForm):
    company = StringField("Company", validators=[Length(min=1, max=255)])
    role = StringField("Role", validators=OPTIONAL_STR)
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])
    responsibilities = TextAreaField("Responsibilities", validators=[Optional(), Length(max=2000)])
    achievements = TextAreaField("Achievements", validators=[Optional(), Length(max=2000)])


class SkillForm(FlaskForm):
    name = StringField("Skill", validators=[Length(min=1, max=120)])
    proficiency = SelectField(
        "Proficiency",
        choices=[("", "Not specified")] + [(p, p.capitalize()) for p in PROFICIENCY_LEVELS],
        validators=[Optional()],
    )


class LanguageForm(FlaskForm):
    name = StringField("Language", validators=[Length(min=1, max=100)])
    level = SelectField(
        "Level", choices=[("", "Not specified")] + [(lvl, lvl) for lvl in CEFR_LEVELS], validators=[Optional()]
    )


class PreferenceForm(FlaskForm):
    fields = StringField("Ausbildung fields (comma-separated)", validators=[Optional(), Length(max=1000)])
    locations = StringField("Preferred locations (comma-separated, blank = Germany-wide)", validators=[Optional(), Length(max=1000)])
    desired_start_date = StringField("Desired start date", validators=[Optional(), Length(max=20)])
    min_german_level = SelectField(
        "Minimum German level",
        choices=[("", "Not specified")] + [(lvl, lvl) for lvl in CEFR_LEVELS],
        validators=[Optional()],
    )
    max_distance_km = IntegerField("Max distance (km)", validators=[Optional()])
    open_to_relocation = BooleanField("Open to relocation")
    other_notes = TextAreaField("Other preferences", validators=[Optional(), Length(max=2000)])
