from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, DateField, TextAreaField
from wtforms.validators import Optional, NumberRange, Length

from app.models.access_code import CODE_TYPES


class CreateCodeForm(FlaskForm):
    code_type = SelectField(_l("Type"), choices=lambda: [(t, t.capitalize()) for t in CODE_TYPES])
    max_uses = IntegerField(_l("Max uses"), default=1, validators=[NumberRange(min=1, max=100000)])
    expires_at = DateField(_l("Expires on (optional)"), validators=[Optional()])
    # Plans page + access expiry pass (2026-08-30): None = no auto-expiry,
    # unchanged default behavior. Upper bound (120 months = 10 years) is
    # just a typo guard, not a product limit - nothing about the plans
    # themselves caps this. The admin/codes.html "Plan" convenience
    # selector auto-fills this (1 for monthly plans, 12 for yearly) but it
    # stays a plain, directly-editable field underneath for custom cases.
    access_duration_months = IntegerField(
        _l("Access duration in months (optional)"), validators=[Optional(), NumberRange(min=1, max=120)]
    )
    notes = TextAreaField(_l("Notes (optional)"), validators=[Optional(), Length(max=500)])
