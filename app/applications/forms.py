from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, DateTimeField
from wtforms.validators import Optional, Length, DataRequired

from app.models.application import APPLICATION_STATUSES, APPLICATION_STATUS_LABELS

REQUIRED = _l("This field is required.")


def _max_length_message(max_len):
    return _l("Must be at most %(max)d characters long.", max=max_len)


class CoverLetterForm(FlaskForm):
    content = TextAreaField(
        _l("Cover letter"), validators=[DataRequired(message=REQUIRED), Length(max=20000, message=_max_length_message(20000))]
    )


class EmailForm(FlaskForm):
    subject = StringField(
        _l("Subject"), validators=[DataRequired(message=REQUIRED), Length(max=500, message=_max_length_message(500))]
    )
    body = TextAreaField(
        _l("Body"), validators=[DataRequired(message=REQUIRED), Length(max=10000, message=_max_length_message(10000))]
    )


class FollowUpEmailForm(FlaskForm):
    subject = StringField(
        _l("Subject"), validators=[DataRequired(message=REQUIRED), Length(max=500, message=_max_length_message(500))]
    )
    body = TextAreaField(
        _l("Body"), validators=[DataRequired(message=REQUIRED), Length(max=10000, message=_max_length_message(10000))]
    )


# Screens pass 2 (Application Detail, 2026-08-27): interview prep, CV
# statement, and reply suggestions previously had generate/regenerate
# routes only - no save route, so edited_at (added in the schema pass)
# could never populate. Mirror CoverLetterForm exactly - same shape,
# same mechanism, nothing novel.
class InterviewPrepForm(FlaskForm):
    prep_text = TextAreaField(
        _l("Interview prep"), validators=[DataRequired(message=REQUIRED), Length(max=20000, message=_max_length_message(20000))]
    )


class CvProfileStatementForm(FlaskForm):
    statement_text = TextAreaField(
        _l("CV profile statement"), validators=[DataRequired(message=REQUIRED), Length(max=5000, message=_max_length_message(5000))]
    )


class ReplySuggestionForm(FlaskForm):
    ai_suggested_reply = TextAreaField(
        _l("Suggested reply"), validators=[DataRequired(message=REQUIRED), Length(max=10000, message=_max_length_message(10000))]
    )


class StatusForm(FlaskForm):
    # i18n pass 2: real translated labels (APPLICATION_STATUS_LABELS,
    # app/models/application.py - shared with status_pill()), not
    # status.replace("_", " ").title(), which has no German equivalent.
    status = SelectField(_l("Status"), choices=[(s, APPLICATION_STATUS_LABELS[s]) for s in APPLICATION_STATUSES])
    contact_person = StringField(_l("Contact person"), validators=[Optional(), Length(max=255, message=_max_length_message(255))])
    contact_email = StringField(_l("Contact email"), validators=[Optional(), Length(max=255, message=_max_length_message(255))])
    interview_date = DateTimeField(_l("Interview date/time"), validators=[Optional()], format="%Y-%m-%dT%H:%M")
    follow_up_date = DateField(_l("Follow-up date"), validators=[Optional()])
    notes = TextAreaField(_l("Notes"), validators=[Optional(), Length(max=5000, message=_max_length_message(5000))])
