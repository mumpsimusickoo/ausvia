from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, DateField, TextAreaField
from wtforms.validators import Optional, NumberRange, Length

from app.models.access_code import CODE_TYPES


class CreateCodeForm(FlaskForm):
    code_type = SelectField(_l("Type"), choices=lambda: [(t, t.capitalize()) for t in CODE_TYPES])
    max_uses = IntegerField(_l("Max uses"), default=1, validators=[NumberRange(min=1, max=100000)])
    expires_at = DateField(_l("Expires on (optional)"), validators=[Optional()])
    notes = TextAreaField(_l("Notes (optional)"), validators=[Optional(), Length(max=500)])
