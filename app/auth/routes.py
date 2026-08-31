import sqlalchemy as sa
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_babel import gettext as _
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.access_expiry import compute_access_expiry, is_access_expired
from app.extensions import db, limiter
from app.i18n import refresh_locale, sync_explicit_locale_to_user
from app.mail import send_password_reset_email
from app.models import User, InvitationCode, CodeRedemption, CandidateProfile
from app.models.user import utcnow
from app.plans import whatsapp_display
from app.utils.logging import log_event
from app.auth.forms import RegisterForm, LoginForm, RequestResetForm, ResetPasswordForm

bp = Blueprint("auth", __name__, url_prefix="/auth")

RESET_SALT = "password-reset"


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        code = InvitationCode.query.filter_by(code=form.access_code.data).first()
        if not code:
            flash(_("Invalid access code."), "error")
            return render_template("auth/register.html", form=form)

        valid, error = code.is_valid()
        if not valid:
            flash(error, "error")
            return render_template("auth/register.html", form=form)

        if User.query.filter_by(email=form.email.data.lower()).first():
            flash(_("An account with this email already exists."), "error")
            return render_template("auth/register.html", form=form)

        role = "admin" if code.code_type == "admin" else "user"
        plan = code.code_type if code.code_type != "admin" else "premium"

        user = User(
            email=form.email.data.lower(), role=role, plan=plan,
            marketing_consent=form.marketing_consent.data,
        )
        user.set_password(form.password.data)
        # Plans page + access expiry pass (2026-08-30): only codes created
        # through the admin "Plan" convenience selector set this - every
        # other code type (trial/standard/admin, or a premium code created
        # the old way) leaves it None, meaning no auto-expiry, unchanged
        # from today. redeemed_at computed once here and reused below for
        # CodeRedemption's own timestamp, so both reflect the same instant.
        redeemed_at = utcnow()
        if code.access_duration_months:
            user.access_expires_at = compute_access_expiry(redeemed_at, code.access_duration_months)
        db.session.add(user)
        db.session.flush()  # assigns user.id before we reference it below

        # Phase 7 remediation (QA finding W1): the is_valid() check above is
        # only a fast, friendly rejection for the common case - it reads
        # use_count without holding a lock, so two concurrent requests could
        # both pass it for the same single-use code. The actual enforcement
        # is this atomic conditional UPDATE: the database only lets the
        # increment through if use_count is still below max_uses *at the
        # moment the row is written*, so at most one concurrent request can
        # ever win the last redemption of a code (single-use or otherwise).
        redeemed = db.session.execute(
            sa.update(InvitationCode)
            .where(
                InvitationCode.id == code.id,
                InvitationCode.is_active.is_(True),
                InvitationCode.use_count < InvitationCode.max_uses,
                sa.or_(InvitationCode.expires_at.is_(None), InvitationCode.expires_at >= utcnow()),
            )
            .values(use_count=InvitationCode.use_count + 1)
        )
        if redeemed.rowcount == 0:
            db.session.rollback()
            flash(
                _(
                    "This access code just became invalid (it may have already been used, "
                    "expired, or been deactivated). Please request a new one."
                ),
                "error",
            )
            return render_template("auth/register.html", form=form)

        db.session.add(CodeRedemption(code_id=code.id, user_id=user.id, redeemed_at=redeemed_at))
        db.session.add(CandidateProfile(user_id=user.id, contact_email=user.email))
        # i18n pass 1: if this visitor already made an explicit language
        # choice while anonymous (a real switcher click, cookie-backed -
        # not Accept-Language guesswork), carry it into the new account
        # rather than resetting to the schema default. See app/i18n.py.
        sync_explicit_locale_to_user(user)
        db.session.commit()
        refresh_locale()

        log_event("auth", f"New account registered (plan={plan}).", user_id=user.id)
        login_user(user)
        flash(_("Welcome! Let's set up your candidate profile."), "success")
        return redirect(url_for("profile.view"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data) and user.is_active:
            # Plans page + access expiry pass (2026-08-30), checkpoint 1 of
            # 2 (the other is app/access_expiry.py's mid-session
            # before_request hook). Checked here, after credentials are
            # confirmed valid, so the message can be specific ("your
            # access ended") rather than the generic invalid-credentials
            # one below - the password wasn't wrong, the account just
            # isn't currently entitled to log in.
            if is_access_expired(user):
                flash(
                    _(
                        "Your access period has ended. Contact us on WhatsApp (%(whatsapp)s) to renew.",
                        whatsapp=whatsapp_display(),
                    ),
                    "error",
                )
                log_event("auth", "Login refused: access period has expired.", user_id=user.id, level="warning")
                return render_template("auth/login.html", form=form)
            # i18n pass 1: a locale cookie set by a real switcher click
            # while logged out must survive this login - without this,
            # get_locale() would immediately outrank it with whatever
            # this account's User.locale already held (its own prior
            # explicit choice, or just the untouched schema default for
            # every pre-i18n account). See app/i18n.py.
            sync_explicit_locale_to_user(user)
            db.session.commit()
            refresh_locale()
            login_user(user, remember=form.remember_me.data)
            log_event("auth", "User logged in.", user_id=user.id)
            next_url = request.args.get("next")
            return redirect(next_url or url_for("main.dashboard"))
        flash(_("Invalid email or password."), "error")
        log_event("auth", "Failed login attempt.", level="warning")

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    log_event("auth", "User logged out.", user_id=current_user.id)
    logout_user()
    flash(_("You have been logged out."), "info")
    return redirect(url_for("main.landing"))


@bp.route("/reset-password", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def request_reset():
    """Security fix, 2026-08-30 (see DECISIONS.md): this route used to
    render the real reset link directly on the page, gated behind
    `current_app.config.get("MAIL_PROVIDER_CONFIGURED")` - a key that was
    never actually defined anywhere in config.py, so that check was always
    False and the "no email provider configured, here's the link" fallback
    was permanently active, including in production. Anyone who submitted
    a registered user's email got a valid, working reset link handed
    straight to their own browser - a full account-takeover path requiring
    no access to the victim's inbox at all.

    Fixed by never rendering the link/token anywhere in the response,
    unconditionally - not just "unless a mail provider is configured" (that
    condition never actually worked, and shouldn't be trusted again even if
    it did: the token must never appear in an HTTP response body under any
    config state, only ever in a real, separately-sent email). Same generic
    response whether or not the account exists, unconditionally too - the
    email-enumeration side channel was the other half of this same bug
    (a real account produced a link in the page; a fake one produced
    nothing distinguishable in the old flash-only path, but the *link's
    presence itself* was already the tell).

    Real delivery, 2026-08-30 (later same day - see DECISIONS.md's
    follow-up entry): send_password_reset_email() (app/mail.py) now
    actually emails `reset_link` via Resend when a real account matches.
    It never raises and never exposes the link anywhere but the email
    itself - an unconfigured or failing mail provider silently logs and
    does nothing further, it does NOT fall back to showing the link here.
    That's what keeps this route safe regardless of mail-provider state.
    """
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            token = _serializer().dumps(user.email, salt=RESET_SALT)
            reset_link = url_for("auth.reset_password", token=token, _external=True)
            log_event("auth", "Password reset requested.", user_id=user.id)
            send_password_reset_email(user, reset_link)
        flash(
            _("If an account with that email exists, a password reset link has been sent."),
            "info",
        )
    return render_template("auth/request_reset.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = _serializer().loads(token, salt=RESET_SALT, max_age=3600)
    except SignatureExpired:
        flash(_("This reset link has expired. Please request a new one."), "error")
        return redirect(url_for("auth.request_reset"))
    except BadSignature:
        flash(_("This reset link is invalid."), "error")
        return redirect(url_for("auth.request_reset"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash(_("This reset link is invalid."), "error")
        return redirect(url_for("auth.request_reset"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        log_event("auth", "Password reset completed.", user_id=user.id)
        flash(_("Your password has been reset. Please log in."), "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", form=form)
