"""Real transactional email delivery via Resend (password reset,
2026-08-30 pass - see DECISIONS.md). This is what makes the password
reset flow usable again after the earlier security fix (same date,
DECISIONS.md's first 2026-08-30 entry) removed the on-page link exposure
without replacing it with any real delivery path - until this pass, a
reset request generated a token and logged it internally, but the token
never reached the user anywhere.

Graceful degradation mirrors this app's existing single-provider pattern
(app/documents/storage.py's S3Storage, app/ai/provider_factory.py): if
RESEND_API_KEY isn't configured, or the real send call fails for any
reason, this must NEVER raise, and must NEVER surface the token/reset
link anywhere outside the email itself - that's exactly the
vulnerability the earlier fix removed, and regressing toward it (e.g. by
falling back to showing the link on-page "just this once, since sending
failed") would undo that fix. It only logs the attempt internally
(log_event, admin-visible in /admin) and returns; the caller
(app/auth/routes.py's request_reset()) always shows the same generic,
enumeration-safe message regardless of whether a real email was actually
sent.
"""
from flask import current_app
from flask_babel import force_locale, gettext as _

from app.utils.logging import log_event

FROM_ADDRESS = "AUSVIA <noreply@ausvia.org>"
# Light-mode --brand token (app/static/css/tailwind.css's :root block) -
# hardcoded rather than a CSS variable, since email clients don't reliably
# support them; there's no dark-mode equivalent to pick between here since
# an email has no concept of the recipient's app theme preference.
BRAND_COLOR = "#0b767d"


def _password_reset_content(reset_link):
    """Builds (subject, html, text) in whatever locale is currently
    active - callers wrap this in flask_babel.force_locale(user.locale)
    so the email renders in the account's own stored language preference,
    not whatever locale the anonymous requester's browser happens to be
    sending (the person filling out the forgot-password form may not be
    the account owner, or may be on a different device/browser than
    usual - the account's own stored preference is the correct signal
    for what language the actual recipient reads)."""
    greeting = _("Hi,")
    intro = _(
        "We received a request to reset the password for your AUSVIA "
        "account. Click the button below to choose a new password."
    )
    cta = _("Reset password")
    expiry = _(
        "This link expires in 1 hour. If you didn't request this, you "
        "can safely ignore this email - your password will not be "
        "changed."
    )
    signature = _("The AUSVIA team")
    subject = _("Reset your AUSVIA password")

    html = (
        '<div style="font-family:-apple-system,\'Segoe UI\',Roboto,sans-serif;'
        'max-width:480px;margin:0 auto;padding:24px;color:#101619;">'
        f'<p style="margin:0 0 16px;">{greeting}</p>'
        f'<p style="margin:0 0 24px;line-height:1.5;">{intro}</p>'
        '<p style="text-align:center;margin:0 0 24px;">'
        f'<a href="{reset_link}" style="display:inline-block;background:{BRAND_COLOR};'
        'color:#ffffff;padding:12px 28px;border-radius:8px;text-decoration:none;'
        f'font-weight:600;">{cta}</a>'
        "</p>"
        f'<p style="margin:0 0 24px;color:#55636d;font-size:14px;line-height:1.5;">{expiry}</p>'
        f'<p style="margin:0;color:#55636d;">{signature}</p>'
        "</div>"
    )
    text = f"{greeting}\n\n{intro}\n\n{reset_link}\n\n{expiry}\n\n{signature}"

    return subject, html, text


def send_password_reset_email(user, reset_link):
    """Best-effort send - never raises. See module docstring for the
    graceful-degradation contract this must hold."""
    api_key = current_app.config.get("RESEND_API_KEY")
    if not api_key:
        # No real provider configured (e.g. local dev) - nothing to
        # attempt. Same "absence is fine, not an error" pattern as every
        # other optional provider in this app.
        log_event(
            "auth", "Password reset email not sent: RESEND_API_KEY not configured.",
            level="warning", user_id=user.id,
        )
        return

    # Imported lazily, only once a real key is actually configured -
    # same convention as app/documents/storage.py's boto3 import inside
    # S3Storage.__init__, not at module top level.
    import resend
    from resend.exceptions import ResendError

    resend.api_key = api_key

    with force_locale(user.locale):
        subject, html, text = _password_reset_content(reset_link)

    try:
        resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": user.email,
            "subject": subject,
            "html": html,
            "text": text,
        })
    except ResendError as e:
        log_event(
            "auth", f"Password reset email failed to send: {e}",
            level="warning", user_id=user.id,
        )
    except Exception as e:
        # Catch-all floor, same reasoning as
        # app/ai/providers/gemini_provider.py's bare except: an SDK
        # exception type not covered by ResendError (a connectivity
        # failure, a bug in the SDK itself) must never take down this
        # request or leak the token - it degrades exactly like an
        # unconfigured key does.
        log_event(
            "auth", f"Password reset email failed to send: {e}",
            level="warning", user_id=user.id,
        )
