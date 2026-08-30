"""Plan/pricing definitions for the public plans page (app/main/routes.py's
plans() route) and the WhatsApp-based manual purchase flow. No payment
gateway - payments are explicitly out of scope, handled off-platform (a
plan is purchased by contacting WhatsApp directly; an admin then manually
issues the code via /admin/codes - see PRODUCT.md and DECISIONS.md). This
module is not a billing system: just the numbers and copy the plans page
renders, and the WhatsApp link text the admin "Plan" convenience selector
implicitly matches (see app/admin/forms.py).

Yearly price is derived as monthly x YEARLY_MULTIPLIER (10, not 12) at the
point of use, not stored as a second hardcoded number - the "multiplies by
exactly 10" rule then holds structurally, not just by coincidence of two
lists happening to agree.
"""
from urllib.parse import quote

from flask_babel import gettext as _

# Real WhatsApp number this app's manual purchase flow contacts - not a
# placeholder. Kept as a bare string (no wa.me prefix) so both the plans
# page and the renewal-reminder link below build their URL from one source.
WHATSAPP_NUMBER = "212707935808"

YEARLY_MULTIPLIER = 10

# users -> DH/month. Ordered smallest to largest; the plans page renders
# them in this order.
PLAN_MONTHLY_PRICES_DH = [
    (1, 150),
    (2, 250),
    (5, 500),
]


def yearly_price_dh(monthly_dh):
    return monthly_dh * YEARLY_MULTIPLIER


def whatsapp_display():
    """Short, human-readable reference for plain-text contexts (flash
    messages) - deliberately NOT the full pre-filled URL from the two
    helpers below: a percent-encoded query string dumped as visible plain
    text (this app's flash messages are always plain text, never
    rich/linked - see app/templates/_flashes.html) would be unreadable
    noise there. The full pre-filled links are for real clickable CTAs
    (the plans page's buttons) instead."""
    return f"wa.me/{WHATSAPP_NUMBER}"


def whatsapp_plan_url(users, yearly):
    """Pre-filled WhatsApp link for requesting a specific plan/billing
    period - deliberately specific (not a generic "I'm interested"
    message) so the admin knows what's being asked for before replying."""
    period = _("yearly") if yearly else _("monthly")
    message = _(
        "Hi, I'd like to request the %(users)s-user / %(period)s AUSVIA plan.",
        users=users, period=period,
    )
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(message)}"
