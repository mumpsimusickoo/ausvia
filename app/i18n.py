"""i18n pass 1 (2026-08-28): locale selection, the switcher's cookie/account
persistence, and locale-aware formatting helpers. See DECISIONS.md for the
full reasoning - short version:

- English is the default; German is the second language, toggled by a real
  switcher. This supersedes the AUSVIA 2.0 bundle's own bilingual rule
  (English labels over permanently-German prose) - not the target here.
- Priority order for which locale a request gets: (1) an explicit choice,
  persisted - the `User.locale` column for a logged-in user, a cookie for
  a logged-out one; (2) Accept-Language, but only for a visitor who has
  never made an explicit choice (no cookie, no account); (3) English.
- The cookie and the account column are the same "explicit choice" tier,
  not two competing sources - see sync_explicit_locale_to_user() for how
  they converge at the auth boundary so a choice made while logged out
  survives login/registration, matching how the theme preference already
  survives login via localStorage.
"""

from flask import current_app, has_request_context, request
from flask_babel import format_currency as _format_currency
from flask_babel import format_date as _format_date
from flask_babel import format_datetime as _format_datetime
from flask_babel import refresh as _refresh_babel_locale

LOCALE_COOKIE_NAME = "ausvia_locale"
LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year - a preference, not a session artifact


def supported_locales():
    return list(current_app.config["LANGUAGES"].keys())


def get_locale():
    """The Babel locale_selector callback (app/__init__.py:
    babel.init_app(app, locale_selector=get_locale)). Also importable
    directly wherever the resolved locale is needed outside a Babel
    formatting call.

    current_user.locale is authoritative once a request is authenticated -
    not because a fresh login re-derives anything, but because
    sync_explicit_locale_to_user() (called at login/register) already
    wrote the right value there before this function ever runs on an
    authenticated request. That column is NOT NULL with a default of
    "en" (has been since the very first migration - see DECISIONS.md), so
    for every authenticated request it's a real, always-valid explicit
    choice, never a signal to fall through past.

    Falls straight to the app's default locale when there's no request to
    read a cookie/user/Accept-Language header from at all - `current_user`
    and `request` both need a request context, not just an app context.
    In real usage this never happens (every real caller of a gettext-using
    function runs inside an actual HTTP request), but i18n pass 2 found it
    does happen in this test suite's own established pattern: several
    business-logic functions (compute_priority_digest() among them) are
    exercised directly against just the `app`/`db` fixtures, no `client`
    call, mirroring flask_babel's own get_locale() ("returns None if used
    outside a request" - its own docstring) rather than crashing every one
    of those tests the moment their code path first called _()/ngettext().
    """
    locales = supported_locales()

    if not has_request_context():
        return current_app.config["BABEL_DEFAULT_LOCALE"]

    from flask_login import current_user  # deferred: avoids an app-context import cycle at module load

    if current_user.is_authenticated and current_user.locale in locales:
        return current_user.locale

    cookie_locale = request.cookies.get(LOCALE_COOKIE_NAME)
    if cookie_locale in locales:
        return cookie_locale

    return request.accept_languages.best_match(locales, current_app.config["BABEL_DEFAULT_LOCALE"])


def set_locale_cookie(response, locale):
    """Single call site for the cookie's actual options, so the switcher
    route and any future call site can't drift on samesite/secure/max-age.
    secure mirrors SESSION_COOKIE_SECURE - same non-sensitive-but-still-
    consistent posture as every other cookie this app sets (see Phase 8).
    """
    response.set_cookie(
        LOCALE_COOKIE_NAME,
        locale,
        max_age=LOCALE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
    )


def refresh_locale():
    """Call immediately after anything that changes which locale get_locale()
    should resolve to for the REST of the current request (the switcher
    route, and login/register once sync_explicit_locale_to_user() has run) -
    flask_babel's own get_locale()/gettext caches the first-resolved locale
    on the request/app context and never re-derives it otherwise, so
    without this, a template rendered later in the same request (a flash
    message, a redirect target that renders immediately) could still show
    the locale that was active before the switch. flask_babel.refresh()
    is the documented mechanism for exactly this - see its own docstring
    ("the flash() function would probably return English text and a now
    German page" without it). Wrapped here rather than importing
    flask_babel directly at each call site, same reasoning as the other
    thin wrappers in this module.
    """
    _refresh_babel_locale()


def sync_explicit_locale_to_user(user):
    """Call at login and at registration, before the response is built.
    If the browser is carrying an explicit locale cookie (set by a real
    switcher click while logged out), write it into the account so it
    doesn't get silently overridden by whatever User.locale already held -
    for an existing account, its stored default ("en", untouched since
    registration); for a brand-new account, the schema default. Without
    this, "the choice survives login" (a required verification state)
    would fail the moment an existing account's stale default outranks a
    real anonymous choice the moment get_locale() sees is_authenticated.

    A no-op when there's no cookie (nothing explicit to carry over) or the
    cookie already matches - avoids an unconditional write/commit on every
    login.
    """
    cookie_locale = request.cookies.get(LOCALE_COOKIE_NAME)
    if cookie_locale in supported_locales() and user.locale != cookie_locale:
        user.locale = cookie_locale


def safe_next_path(candidate, default="/"):
    """Same-app-relative-only redirect target for the locale switcher, so
    switching preserves the current page and its query params (a required
    verification state) without opening an open-redirect via a
    scheme-relative or absolute-URL `next` value. Mirrors the trust level
    auth.login's own `next` param already uses (this app's own routes,
    not user-controlled arbitrary hosts), just with an explicit check
    since this route (unlike login) is reachable from a plain unauthenticated
    POST with no login_required gate to narrow who can submit it.
    """
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return default


def format_local_date(dt, format="medium"):
    """Locale-aware date formatting (babel.dates via flask_babel), with
    this codebase's established None -> em-dash convention (see e.g.
    app/main/routes.py:_relative_date) rather than raising or printing
    "None". Proof-of-concept call sites: jobs/detail.html's deadline line,
    applications/detail.html's "applied since" line, and
    main/routes.py's _relative_date() absolute-date branch - see
    DECISIONS.md for why these three and not a mass conversion (pass 2).
    """
    if dt is None:
        return "—"
    return _format_date(dt, format=format)


def format_local_datetime(dt, format="medium"):
    """Locale-aware date+time formatting (babel.dates via flask_babel),
    same None-safety convention as format_local_date(). Added in i18n
    pass 2 alongside the mass date-formatting sweep: several real call
    sites (job radar's "checked" timestamp, interview date/time,
    Gmail-reply timestamps) need the time component format_local_date()
    deliberately doesn't carry - a separate helper rather than overloading
    format_local_date() with an optional time flag, so each call site's
    intent (a bare date vs. a date-and-time) stays visible at the call
    site itself.
    """
    if dt is None:
        return "—"
    return _format_datetime(dt, format=format)


def format_local_currency(amount, currency="EUR"):
    """Locale-aware currency formatting (babel.numbers via flask_babel).
    Built and ready, deliberately NOT wired into any live template this
    pass: Job.salary (the one money-shaped field in the schema) is a
    pre-formatted free-text string from each source adapter (Arbeitsagentur's
    verguetungsangabe text, Adzuna's own min-max string), not a numeric
    amount - there is no real numeric currency value anywhere in this
    app's data to format. Demonstrated with a literal example value at
    /admin/components instead of against live data, same reasoning as
    Job Detail's dropped "duration" tile: don't fabricate a call site a
    real field doesn't back. See DECISIONS.md.
    """
    if amount is None:
        return "—"
    return _format_currency(amount, currency)
