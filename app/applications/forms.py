from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, DateTimeField
from wtforms.validators import Optional, Length, DataRequired

from app.models.application import APPLICATION_STATUSES


class CoverLetterForm(FlaskForm):
    content = TextAreaField("Cover letter", validators=[DataRequired(), Length(max=20000)])


class EmailForm(FlaskForm):
    subject = StringField("Subject", validators=[DataRequired(), Length(max=500)])
    body = TextAreaField("Body", validators=[DataRequired(), Length(max=10000)])


class FollowUpEmailForm(FlaskForm):
    subject = StringField("Subject", validators=[DataRequired(), Length(max=500)])
    body = TextAreaField("Body", validators=[DataRequired(), Length(max=10000)])


class StatusForm(FlaskForm):
    status = SelectField("Status", choices=[(s, s.replace("_", " ").title()) for s in APPLICATION_STATUSES])
    contact_person = StringField("Contact person", validators=[Optional(), Length(max=255)])
    contact_email = StringField("Contact email", validators=[Optional(), Length(max=255)])
    interview_date = DateTimeField("Interview date/time", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    follow_up_date = DateField("Follow-up date", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])
