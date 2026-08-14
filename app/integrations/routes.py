from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user

from app.integrations import gmail_oauth
from app.utils.logging import log_event

bp = Blueprint("integrations", __name__, url_prefix="/integrations")

STATE_SESSION_KEY = "gmail_oauth_state"


@bp.route("/gmail")
@login_required
def gmail_status():
    connection = gmail_oauth.get_connection(current_user)
    return render_template(
        "integrations/gmail.html",
        connection=connection,
        configured=gmail_oauth.is_configured(),
    )


@bp.route("/gmail/connect")
@login_required
def gmail_connect():
    if not gmail_oauth.is_configured():
        flash(
            "Gmail isn't configured yet - an admin needs to set GOOGLE_CREDENTIALS_JSON "
            "or add credentials.json. See README.md.",
            "error",
        )
        return redirect(url_for("integrations.gmail_status"))

    try:
        auth_url, state = gmail_oauth.get_authorization_url()
    except Exception as e:
        # Phase 8 security audit (2.6): this used to flash str(e) straight to
        # the user - the same class of bug W3 fixed for background-task
        # errors, just in a spot that fix didn't reach. get_authorization_url
        # calls into google-auth-oauthlib, whose exceptions aren't ours to
        # guarantee never echo request/response detail, so raw text stays
        # server-side in the log only, same pattern as W3.
        flash("Could not start the Gmail connection. Please try again.", "error")
        log_event("gmail", f"Failed to start OAuth flow: {e}", level="error", user_id=current_user.id)
        return redirect(url_for("integrations.gmail_status"))

    # CSRF-safety for the OAuth round trip itself, independent of the app's
    # own CSRF tokens - this is the standard oauthlib "state" pattern.
    session[STATE_SESSION_KEY] = state
    return redirect(auth_url)


@bp.route("/gmail/callback")
@login_required
def gmail_callback():
    expected_state = session.pop(STATE_SESSION_KEY, None)
    returned_state = request.args.get("state")

    if request.args.get("error"):
        flash("Gmail connection was cancelled or denied.", "info")
        return redirect(url_for("integrations.gmail_status"))

    if not expected_state or expected_state != returned_state:
        flash("Gmail connection failed - the request could not be verified. Please try again.", "error")
        log_event("gmail", "OAuth callback state mismatch.", level="warning", user_id=current_user.id)
        return redirect(url_for("integrations.gmail_status"))

    try:
        credentials = gmail_oauth.exchange_code(expected_state, request.url)
        gmail_oauth.save_connection(current_user, credentials)
    except Exception as e:
        # Phase 8 security audit (2.6): same reasoning as gmail_connect above
        # - exchange_code() makes a real network call to Google's token
        # endpoint carrying this app's own client_secret (from
        # credentials.json), so an unsanitized exception here is a real,
        # not just theoretical, place a secret could end up in a user-facing
        # response. Raw detail stays server-side in the log only.
        flash("Could not complete the Gmail connection. Please try again.", "error")
        log_event("gmail", f"OAuth token exchange failed: {e}", level="error", user_id=current_user.id)
        return redirect(url_for("integrations.gmail_status"))

    log_event("gmail", "Gmail account connected.", user_id=current_user.id)
    flash("Gmail connected.", "success")
    return redirect(url_for("integrations.gmail_status"))


@bp.route("/gmail/disconnect", methods=["POST"])
@login_required
def gmail_disconnect():
    gmail_oauth.disconnect(current_user)
    log_event("gmail", "Gmail account disconnected.", user_id=current_user.id)
    flash("Gmail disconnected.", "info")
    return redirect(url_for("integrations.gmail_status"))
