import sqlalchemy as sa
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db, limiter
from app.models import User, InvitationCode, CodeRedemption, CandidateProfile
from app.models.user import utcnow
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
            flash("Invalid access code.", "error")
            return render_template("auth/register.html", form=form)

        valid, error = code.is_valid()
        if not valid:
            flash(error, "error")
            return render_template("auth/register.html", form=form)

        if User.query.filter_by(email=form.email.data.lower()).first():
            flash("An account with this email already exists.", "error")
            return render_template("auth/register.html", form=form)

        role = "admin" if code.code_type == "admin" else "user"
        plan = code.code_type if code.code_type != "admin" else "premium"

        user = User(email=form.email.data.lower(), role=role, plan=plan)
        user.set_password(form.password.data)
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
                "This access code just became invalid (it may have already been used, "
                "expired, or been deactivated). Please request a new one.",
                "error",
            )
            return render_template("auth/register.html", form=form)

        db.session.add(CodeRedemption(code_id=code.id, user_id=user.id))
        db.session.add(CandidateProfile(user_id=user.id, contact_email=user.email))
        db.session.commit()

        log_event("auth", f"New account registered (plan={plan}).", user_id=user.id)
        login_user(user)
        flash("Welcome! Let's set up your candidate profile.", "success")
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
            login_user(user, remember=form.remember_me.data)
            log_event("auth", "User logged in.", user_id=user.id)
            next_url = request.args.get("next")
            return redirect(next_url or url_for("main.dashboard"))
        flash("Invalid email or password.", "error")
        log_event("auth", "Failed login attempt.", level="warning")

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    log_event("auth", "User logged out.", user_id=current_user.id)
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.landing"))


@bp.route("/reset-password", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def request_reset():
    form = RequestResetForm()
    reset_link = None
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            token = _serializer().dumps(user.email, salt=RESET_SALT)
            reset_link = url_for("auth.reset_password", token=token, _external=True)
            log_event("auth", "Password reset requested.", user_id=user.id)
        # Always show the same message whether or not the account exists, so this
        # endpoint can't be used to enumerate registered emails.
        flash(
            "If an account with that email exists, a reset link has been generated.",
            "info",
        )
        if current_app.config.get("MAIL_PROVIDER_CONFIGURED"):
            reset_link = None  # a real provider would have emailed it instead
    return render_template("auth/request_reset.html", form=form, reset_link=reset_link)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = _serializer().loads(token, salt=RESET_SALT, max_age=3600)
    except SignatureExpired:
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.request_reset"))
    except BadSignature:
        flash("This reset link is invalid.", "error")
        return redirect(url_for("auth.request_reset"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("This reset link is invalid.", "error")
        return redirect(url_for("auth.request_reset"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        log_event("auth", "Password reset completed.", user_id=user.id)
        flash("Your password has been reset. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", form=form)
