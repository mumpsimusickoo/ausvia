from datetime import date, datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_babel import gettext as _
from flask_babel import ngettext
from flask_login import login_required, current_user

from app.ai.dashboard_insight import MIN_APPLICATIONS_FOR_INSIGHT, generate_dashboard_insight, get_dashboard_insight
from app.ai.provider import AIProviderError
from app.applications.status_route import latest_transition_at
from app.extensions import db
from app.i18n import format_local_date, refresh_locale, safe_next_path, set_locale_cookie, supported_locales
from app.jobs.adapters.manager import ADMIN_ONLY_SOURCES, get_enabled_adapter_names, KNOWN_SOURCES
from app.models.job import SavedJob, JobRadarStatus
from app.models.application import Application
from app.models.profile import CHECKLIST_LABEL_TRANSLATIONS
from app.plans import PLAN_MONTHLY_PRICES_DH, whatsapp_plan_url, yearly_price_dh
from app.priority_digest import ACTIVE_STATUSES, TERMINAL_STATUSES, compute_priority_digest
from app.jobs.matching import get_or_compute_match
from app.utils.logging import log_event

bp = Blueprint("main", __name__)

# Dashboard applications table: a quick-glance list, not the full history -
# "View all" goes to the real applications list page (out of this pass's
# scope). Capped rather than paginated, matching every other dashboard
# rail card's "show a handful, link to the rest" shape.
DASHBOARD_APPLICATIONS_LIMIT = 8

# Impressum/privacy pass (2026-08-31): fixed publish date for the privacy
# policy's "Last updated" line - update this constant (and re-verify the
# page's content still matches it) whenever the policy text itself
# genuinely changes, not on every deploy.
PRIVACY_POLICY_LAST_UPDATED = date(2026, 8, 31)


def _time_of_day_greeting():
    # Server local time - a reasonable default for now; per-user timezone
    # would need a stored profile preference, tracked as future polish.
    hour = datetime.now().hour
    if hour < 12:
        return _("Good morning")
    if hour < 18:
        return _("Good afternoon")
    return _("Good evening")


def _relative_date(dt):
    """Screens pass 3 (Dashboard, 2026-08-27): humanized date for the
    applications table and the hero card's staleness marker. Absolute
    beyond 13 days - a relative date stops being useful ("47 days ago"
    reads worse than the actual date) and the bundle's own dashboard mock
    mixes relative and absolute for exactly this reason (recent items get
    "seit 3 Tagen"/"gestern", an older one just shows "27.08.2026")."""
    if dt is None:
        return "—"
    days = (datetime.now() - dt).days
    if days <= 0:
        return _("today")
    if days == 1:
        return _("yesterday")
    if days < 14:
        return ngettext("%(num)d day ago", "%(num)d days ago", days)
    # i18n pass 1: locale-aware beyond the relative window, one of this
    # pass's three proof-of-concept call sites for format_local_date() -
    # was a hardcoded German-style %d.%m.%Y regardless of locale before
    # this pass (a real pre-existing inconsistency for English UI users,
    # fixed here as a side effect, not chased down at every other
    # strftime call site - that's pass 2's mass extraction, not this one's
    # infrastructure-proof scope). See DECISIONS.md.
    return format_local_date(dt)


def _situation_summary(digest_items):
    """One real sentence, not the bundle's literal text - computed from
    actual digest data (Screens pass 3, 2026-08-27). "Nothing urgent" is
    the honest default for a healthy account, not an edge case to
    apologize for."""
    if not digest_items:
        return _("Nothing urgent right now — good time to keep applying.")
    n = len(digest_items)
    summary = ngettext(
        "%(num)d item needs your attention this week.",
        "%(num)d items need your attention this week.",
        n,
    )
    # i18n pass 2: reason_codes, not the translated `reasons` text - see
    # priority_digest.py's DigestItem docstring. Substring-matching a
    # translated sentence for "deadline" only ever worked by coincidence
    # of it still being English.
    if any("deadline_soon" in item.reason_codes for item in digest_items):
        summary += " " + _("One has a deadline coming up.")
    return summary


@bp.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    # Screens pass 7 (Landing, 2026-08-28): the footer's source list is
    # generated from whichever adapters are actually enabled AND configured
    # right now (get_enabled_adapter_names() - app/jobs/adapters/manager.py),
    # never hardcoded to the bundle's three. "manual" is excluded - it's a
    # user-driven one-URL-at-a-time import, not something AUSVIA searches on
    # a visitor's behalf, so it doesn't belong in a "we search these
    # sources" claim. ADMIN_ONLY_SOURCES (Jooble, admin-only scoping pass,
    # 2026-08-29) is excluded for the same reason a logged-out visitor is
    # never an admin - this page is pre-auth by definition (authenticated
    # users are redirected away above), so the claim here must stay
    # accurate for that audience regardless of Jooble's own is_enabled
    # toggle.
    source_names = [
        name for name in get_enabled_adapter_names()
        if name != "manual" and name not in ADMIN_ONLY_SOURCES
    ]
    source_display_names = [KNOWN_SOURCES[name] for name in source_names]
    return render_template("landing.html", source_display_names=source_display_names)


@bp.route("/plans")
def plans():
    # Plans page + access expiry pass (2026-08-30): public, pre-auth
    # marketing page - same redirect-authenticated-users-away convention
    # landing() already uses above, since an existing account has no use
    # for a page about requesting one. No payment gateway; each card's CTA
    # is a WhatsApp link naming that specific plan - see PRODUCT.md/
    # DECISIONS.md for why (payments are explicitly out of scope, handled
    # off-platform) and app/plans.py for the actual numbers/link-building.
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    plan_rows = [
        {
            "users": users,
            "monthly_dh": monthly_dh,
            "yearly_dh": yearly_price_dh(monthly_dh),
            "whatsapp_monthly_url": whatsapp_plan_url(users, yearly=False),
            "whatsapp_yearly_url": whatsapp_plan_url(users, yearly=True),
        }
        for users, monthly_dh in PLAN_MONTHLY_PRICES_DH
    ]
    return render_template("plans.html", plan_rows=plan_rows)


@bp.route("/impressum")
def impressum():
    # Impressum/privacy pass (2026-08-31): a real legal-notice page (§ 5
    # DDG), not stubbed - see DECISIONS.md's 2026-08-28 entry for why this
    # was deliberately deferred rather than improvised at the time. No
    # redirect-authenticated-users-away here (unlike plans() above) - an
    # Impressum is a standing legal disclosure that has to stay reachable
    # regardless of login state, not a pre-signup marketing page.
    return render_template("impressum.html")


@bp.route("/privacy")
def privacy():
    # Same page, same reasoning as impressum() above - a real privacy
    # policy, reachable regardless of login state. PRIVACY_POLICY_LAST_UPDATED
    # is a fixed publish date (not datetime.now()) - the "Last updated" line
    # should reflect when the policy content itself last changed, not
    # today's date on every page load.
    return render_template(
        "privacy.html",
        last_updated=format_local_date(PRIVACY_POLICY_LAST_UPDATED, format="long"),
    )


@bp.route("/health")
def health():
    # Used by the hosting platform to know the process is up - deliberately
    # no auth, no DB/dependency check, no version info: just "the WSGI
    # process is alive and answering requests."
    return "ok", 200


@bp.route("/diagnostics/arbeitsagentur-cors-test")
def arbeitsagentur_cors_test():
    # Temporary diagnostic, not a feature - answers whether a browser
    # request to the Arbeitsagentur Jobsuche API works from *our* deployed
    # origin specifically (server-side calls are confirmed blocked; this
    # checks the client-side path). No auth, deliberately unlinked from
    # navigation. Remove this route + its template + the matching
    # connect-src CSP carve-out (app/security_headers.py,
    # DIAGNOSTIC_CORS_TEST_PATH) once the finding is confirmed either way.
    return render_template("diagnostics/arbeitsagentur_cors_test.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    profile = current_user.profile
    saved_job_count = SavedJob.query.filter_by(user_id=current_user.id).count()

    applications = Application.query.filter_by(user_id=current_user.id).all()
    applications_sent = sum(1 for a in applications if a.status not in ("preparing", "ready"))
    interviews = sum(1 for a in applications if a.status == "interview")
    # Was hardcoded to 0 - compute_priority_digest()'s own per-application
    # check already identifies exactly this ("Follow-up date has arrived");
    # counting it directly here is the same real signal, not a second
    # definition of "due" to keep in sync.
    today = date.today()
    follow_ups_due = sum(1 for a in applications if a.follow_up_date and a.follow_up_date <= today)
    active_count = sum(1 for a in applications if a.status in ACTIVE_STATUSES)
    terminal_count = sum(1 for a in applications if a.status in TERMINAL_STATUSES)

    digest_items = compute_priority_digest(current_user)
    hero_item = digest_items[0] if digest_items else None
    hero_staleness = None
    hero_application = None
    if hero_item and hero_item.kind == "application":
        hero_application = next((a for a in applications if a.id == hero_item.url_kwargs.get("application_id")), None)
        if hero_application:
            days = (datetime.now() - latest_transition_at(hero_application)).days
            if days >= 1:
                hero_staleness = ngettext("unchanged for %(num)d day", "unchanged for %(num)d days", days)

    dashboard_applications = sorted(applications, key=latest_transition_at, reverse=True)[:DASHBOARD_APPLICATIONS_LIMIT]
    applications_table = [
        {"application": a, "date_label": _relative_date(latest_transition_at(a))}
        for a in dashboard_applications
    ]

    radar_status = JobRadarStatus.query.filter_by(user_id=current_user.id).first()
    radar_new_count = radar_status.new_job_count if radar_status else 0

    insight = get_dashboard_insight(current_user) if len(applications) >= MIN_APPLICATIONS_FOR_INSIGHT else None

    return render_template(
        "main/dashboard.html",
        greeting=_time_of_day_greeting(),
        # A brand-new invite-only account: distinguishes "nothing urgent"
        # (healthy) from "nothing here yet" (needs a first action) so the
        # empty-state copy can tell them apart honestly.
        is_brand_new=(len(applications) == 0 and saved_job_count == 0),
        profile=profile,
        # i18n pass 2: locale-aware weekday/month names via format_local_date
        # (was strftime('%A, %d %B %Y') - always English regardless of UI
        # language). .upper() dropped from here too - the template now
        # applies it as a CSS text-transform instead of baking a case
        # transform into the translated string itself.
        today_label=format_local_date(datetime.now(), format="full"),
        situation_summary=_situation_summary(digest_items),
        saved_job_count=saved_job_count,
        applications_count=len(applications),
        applications_sent=applications_sent,
        interviews=interviews,
        follow_ups_due=follow_ups_due,
        active_count=active_count,
        terminal_count=terminal_count,
        completeness=profile.completeness_percent() if profile else 0,
        # i18n pass 2: translated labels (CHECKLIST_LABEL_TRANSLATIONS,
        # app/models/profile.py) - completeness_checklist()'s own labels
        # stay untranslated internal keys, see its docstring.
        completeness_missing=[
            CHECKLIST_LABEL_TRANSLATIONS[label] for label, ok in profile.completeness_checklist() if not ok
        ] if profile else [],
        digest_items=digest_items,
        hero_item=hero_item,
        hero_staleness=hero_staleness,
        applications_table=applications_table,
        applications_shown_all=len(applications) <= DASHBOARD_APPLICATIONS_LIMIT,
        hero_application=hero_application,
        radar_status=radar_status,
        radar_new_count=radar_new_count,
        dashboard_insight=insight,
        min_applications_for_insight=MIN_APPLICATIONS_FOR_INSIGHT,
    )


@bp.route("/dashboard/insight", methods=["POST"])
@login_required
def generate_insight():
    applications = Application.query.filter_by(user_id=current_user.id).all()
    if len(applications) < MIN_APPLICATIONS_FOR_INSIGHT:
        flash("Add at least two applications before generating a cross-application insight.", "error")
        return redirect(url_for("main.dashboard"))

    match_by_job_id = {a.job_id: get_or_compute_match(current_user, a.job) for a in applications}
    try:
        generate_dashboard_insight(current_user, applications, match_by_job_id)
        flash("Insight generated.", "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Dashboard insight generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("main.dashboard"))


@bp.route("/digest")
@login_required
def priority_digest():
    return render_template("main/digest.html", items=compute_priority_digest(current_user))


@bp.route("/set-locale", methods=["POST"])
def set_locale():
    """i18n pass 1: the language_switcher() component's target
    (_components.html), called from three chrome contexts (desktop top
    bar, mobile topbar, landing header) - deliberately not @login_required,
    since the landing page has no user. `next` preserves the current page
    and its query params (a required verification state - switching
    language on a filtered search shouldn't drop the filters), validated
    through safe_next_path() rather than trusted verbatim. If authenticated,
    the choice is written straight to the account (the same "explicit
    choice, persisted" tier the cookie occupies for a logged-out visitor -
    see app/i18n.py), not just the cookie, so it survives across devices
    the same way logging in already carries a prior anonymous choice over
    (sync_explicit_locale_to_user(), called at login/register)."""
    lang = request.form.get("lang")
    if lang not in supported_locales():
        abort(400)

    if current_user.is_authenticated:
        current_user.locale = lang
        db.session.commit()

    # flask_babel caches the resolved locale per request/app context and
    # never re-derives it on its own - without this, a flash message or
    # any other content rendered later in the very same request could
    # still reflect the pre-switch locale. See app/i18n.py's docstring.
    refresh_locale()

    response = redirect(safe_next_path(request.form.get("next")))
    set_locale_cookie(response, lang)
    return response
