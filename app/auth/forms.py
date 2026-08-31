from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Regexp

CODE_REGEXP = r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"

# WTForms' own built-in validators (DataRequired, Email, Length, ...) carry
# hardcoded English default messages baked into the wtforms package itself -
# pybabel extract can't see them (they live outside app/), and Babel can't
# translate a string it never extracted. Every validator below that can
# actually fail gets an explicit message= override so its error text is a
# real, translated string this app owns, not a permanently-English one.
REQUIRED = _l("This field is required.")


class RegisterForm(FlaskForm):
    access_code = StringField(
        _l("Access code"),
        validators=[
            DataRequired(message=REQUIRED),
            Regexp(CODE_REGEXP, message=_l("Format: XXXX-XXXX-XXXX")),
        ],
        filters=[lambda v: v.strip().upper() if v else v],
    )
    email = StringField(
        _l("Email"),
        validators=[
            DataRequired(message=REQUIRED),
            Email(message=_l("Please enter a valid email address.")),
            Length(max=255, message=_l("Must be at most %(max)d characters long.")),
        ],
    )
    password = PasswordField(
        _l("Password"),
        validators=[
            DataRequired(message=REQUIRED),
            Length(min=8, max=128, message=_l("Must be between %(min)d and %(max)d characters long.")),
        ],
    )
    confirm_password = PasswordField(
        _l("Confirm password"),
        validators=[
            DataRequired(message=REQUIRED),
            EqualTo("password", message=_l("Passwords must match.")),
        ],
    )
    # Impressum/privacy/registration-consent pass (2026-08-31): a
    # BooleanField's data is False (not empty/None) when unchecked, and
    # DataRequired's own check (`not field.data`) already treats that as
    # missing - `not False == True` - so this is a real, working "must be
    # checked to submit" gate, not merely decorative. Server-side is the
    # actual enforcement (form.validate_on_submit() in
    # app/auth/routes.py's register() rejects the whole submission if this
    # fails, same as any other required field) - the browser's own native
    # `required` attribute (WTForms auto-renders one for any
    # DataRequired-validated field) is a UX nicety on top, never trusted
    # alone, same discipline as every other required field in this app.
    age_confirmed = BooleanField(
        _l("I confirm I am 16 years of age or older."),
        validators=[DataRequired(message=_l("You must confirm you are 16 years of age or older to register."))],
    )
    # Deliberately NO validators at all, and deliberately a separate field
    # from age_confirmed above, never rendered inside the same fieldset/
    # requirement - GDPR requires marketing consent to be freely given on
    # its own, not bundled with (or implied by) any other required
    # checkbox. Defaults to unchecked (WTForms' BooleanField default,
    # matching User.marketing_consent's own False column default) -
    # persisted as-is onto User.marketing_consent in register(), never
    # inferred or defaulted to True anywhere.
    marketing_consent = BooleanField(
        _l("I'd like to receive occasional emails about new features and updates from AUSVIA.")
    )


class LoginForm(FlaskForm):
    email = StringField(
        _l("Email"),
        validators=[DataRequired(message=REQUIRED), Email(message=_l("Please enter a valid email address."))],
    )
    password = PasswordField(_l("Password"), validators=[DataRequired(message=REQUIRED)])
    remember_me = BooleanField(_l("Remember me"))


class RequestResetForm(FlaskForm):
    email = StringField(
        _l("Email"),
        validators=[DataRequired(message=REQUIRED), Email(message=_l("Please enter a valid email address."))],
    )


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        _l("New password"),
        validators=[
            DataRequired(message=REQUIRED),
            Length(min=8, max=128, message=_l("Must be between %(min)d and %(max)d characters long.")),
        ],
    )
    confirm_password = PasswordField(
        _l("Confirm new password"),
        validators=[
            DataRequired(message=REQUIRED),
            EqualTo("password", message=_l("Passwords must match.")),
        ],
    )
