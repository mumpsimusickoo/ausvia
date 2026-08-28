"""i18n pass 1, 2026-08-28 - locale selection (app/i18n.py), the switcher
route, cookie/account persistence at the auth boundary, and the two
proof-of-concept surfaces (sidebar nav strings, format_local_date() call
sites). AI prompt language and mass string extraction are out of scope -
see DECISIONS.md/ROADMAP.md for what's deferred to passes 2 and 3."""

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from flask_babel import force_locale
from flask_login import login_user

from app.i18n import (
    LOCALE_COOKIE_NAME,
    format_local_currency,
    format_local_date,
    get_locale,
    safe_next_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# get_locale() priority: explicit choice > Accept-Language > English default
# ---------------------------------------------------------------------------

def test_defaults_to_english_with_no_signals(app):
    with app.test_request_context("/"):
        assert get_locale() == "en"


def test_uses_cookie_when_present(app):
    with app.test_request_context("/", headers={"Cookie": f"{LOCALE_COOKIE_NAME}=de"}):
        assert get_locale() == "de"


def test_ignores_unsupported_cookie_value(app):
    with app.test_request_context("/", headers={"Cookie": f"{LOCALE_COOKIE_NAME}=fr"}):
        assert get_locale() == "en"


def test_falls_back_to_accept_language_with_no_cookie(app):
    with app.test_request_context("/", headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.5"}):
        assert get_locale() == "de"


def test_accept_language_never_consulted_when_cookie_present(app):
    # A German-browser visitor who already explicitly chose English (cookie)
    # must not be flipped back to German by their own browser header.
    with app.test_request_context(
        "/", headers={"Cookie": f"{LOCALE_COOKIE_NAME}=en", "Accept-Language": "de"}
    ):
        assert get_locale() == "en"


def test_authenticated_users_column_governs_over_a_stray_cookie(app, make_user):
    # Simulates a locale cookie that's out of sync with the account (a
    # different device, a manually cleared cookie store, etc.) - once
    # authenticated, User.locale is the source of truth, not the cookie.
    # See app/i18n.py's get_locale() docstring for why this is safe: it's
    # always a real, valid explicit choice (NOT NULL, defaulted "en" since
    # the very first migration), never a signal to fall through past.
    user = make_user(email="stale-cookie@example.com")
    user.locale = "de"
    from app.extensions import db

    db.session.commit()

    with app.test_request_context("/", headers={"Cookie": f"{LOCALE_COOKIE_NAME}=en"}):
        login_user(user)
        assert get_locale() == "de"


# ---------------------------------------------------------------------------
# safe_next_path() - no open redirect via the switcher's `next` field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "candidate,expected",
    [
        ("/jobs/search?keywords=x&min_score=50", "/jobs/search?keywords=x&min_score=50"),
        ("/dashboard", "/dashboard"),
        (None, "/"),
        ("", "/"),
        ("http://evil.example/", "/"),
        ("//evil.example/", "/"),
        ("javascript:alert(1)", "/"),
    ],
)
def test_safe_next_path(candidate, expected, app):
    with app.test_request_context("/"):
        assert safe_next_path(candidate) == expected


# ---------------------------------------------------------------------------
# The switcher route: POST /set-locale
# ---------------------------------------------------------------------------

def test_set_locale_rejects_unsupported_language(client):
    resp = client.post("/set-locale", data={"lang": "fr", "next": "/"})
    assert resp.status_code == 400


def test_set_locale_sets_cookie_and_preserves_next_with_query_params(client):
    resp = client.post(
        "/set-locale",
        data={"lang": "de", "next": "/jobs/search?keywords=Elektroniker&min_score=50"},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/jobs/search?keywords=Elektroniker&min_score=50"
    set_cookie_header = resp.headers.get("Set-Cookie", "")
    assert f"{LOCALE_COOKIE_NAME}=de" in set_cookie_header


def test_set_locale_falls_back_to_root_for_an_unsafe_next(client):
    resp = client.post("/set-locale", data={"lang": "de", "next": "http://evil.example/"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_switch_round_trip_changes_nav_strings_and_switching_back_restores_them(
    client, db, make_user
):
    # The required end-to-end proof: en -> de -> en, live, on the sidebar
    # nav - the pass's own chosen proof-of-concept strings.
    make_user(email="switcher@example.com", password="Password123!")
    client.post(
        "/auth/login",
        data={"email": "switcher@example.com", "password": "Password123!"},
        follow_redirects=True,
    )

    body_en = client.get("/dashboard").data.decode("utf-8")
    assert "Find Ausbildung" in body_en
    assert "Ausbildung finden" not in body_en

    client.post("/set-locale", data={"lang": "de", "next": "/dashboard"})
    body_de = client.get("/dashboard").data.decode("utf-8")
    assert "Ausbildung finden" in body_de
    assert "Gespeicherte Stellen" in body_de
    assert "Bewerbungen" in body_de
    assert "Kandidatenprofil" in body_de
    assert "Dokumente" in body_de

    client.post("/set-locale", data={"lang": "en", "next": "/dashboard"})
    body_en_again = client.get("/dashboard").data.decode("utf-8")
    assert "Find Ausbildung" in body_en_again
    assert "Ausbildung finden" not in body_en_again


def test_choice_survives_a_reload(client):
    client.post("/set-locale", data={"lang": "de", "next": "/"})
    # Two independent GETs, same client (cookie jar persists) - simulates
    # a page reload, not a single request.
    first = client.get("/").data.decode("utf-8")
    second = client.get("/").data.decode("utf-8")
    assert 'aria-current="true"' in first
    assert 'aria-current="true"' in second


# ---------------------------------------------------------------------------
# Survives login / registration - the explicit choice converges into the
# account so it isn't silently overridden the moment current_user exists.
# ---------------------------------------------------------------------------

def test_choice_survives_login_for_an_existing_account(client, db, make_user):
    # The account's own stored locale is the untouched schema default
    # ("en") - without login-time sync, logging in would silently flip an
    # anonymous German choice back to English.
    user = make_user(email="survives-login@example.com", password="Password123!")
    assert user.locale == "en"

    client.post("/set-locale", data={"lang": "de", "next": "/"})
    client.post(
        "/auth/login",
        data={"email": "survives-login@example.com", "password": "Password123!"},
        follow_redirects=True,
    )

    db.session.refresh(user)
    assert user.locale == "de"
    body = client.get("/dashboard").data.decode("utf-8")
    assert "Ausbildung finden" in body


def test_registration_seeds_locale_from_the_anonymous_cookie(client, db, trial_code):
    client.post("/set-locale", data={"lang": "de", "next": "/"})
    client.post(
        "/auth/register",
        data={
            "access_code": trial_code.code,
            "email": "fresh-german@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )

    from app.models import User

    user = User.query.filter_by(email="fresh-german@example.com").first()
    assert user is not None
    assert user.locale == "de"


def test_registration_with_no_cookie_keeps_the_english_default(client, db, trial_code):
    client.post(
        "/auth/register",
        data={
            "access_code": trial_code.code,
            "email": "fresh-default@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )

    from app.models import User

    user = User.query.filter_by(email="fresh-default@example.com").first()
    assert user is not None
    assert user.locale == "en"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def test_format_local_date_none_safe(app):
    with app.test_request_context("/"):
        assert format_local_date(None) == "—"


def test_format_local_currency_none_safe(app):
    with app.test_request_context("/"):
        assert format_local_currency(None) == "—"


def test_format_local_date_is_locale_aware(app):
    d = date(2027, 9, 1)
    with app.test_request_context("/"):
        with force_locale("en"):
            en = format_local_date(d)
        with force_locale("de"):
            de = format_local_date(d)
    assert en != de
    assert "Sep" in en
    assert "2027" in en
    assert "01.09.2027" == de or "1.9.2027" == de  # babel's exact de 'medium' rendering


def test_format_local_currency_is_locale_aware(app):
    with app.test_request_context("/"):
        with force_locale("en"):
            en = format_local_currency(1150)
        with force_locale("de"):
            de = format_local_currency(1150)
    assert en != de
    assert en.strip().startswith("€") or "1,150" in en  # en-locale ordering
    assert "1.150" in de  # de-locale thousands separator


def test_deadline_line_on_job_detail_uses_the_locale_aware_helper(client, db, make_user):
    from app.models.job import Job

    make_user(email="deadline-viewer@example.com", password="Password123!")
    client.post(
        "/auth/login",
        data={"email": "deadline-viewer@example.com", "password": "Password123!"},
        follow_redirects=True,
    )
    job = Job(
        dedup_key="i18n-deadline-test",
        employment_type="Ausbildung",
        title="Elektroniker",
        application_deadline=date(2027, 9, 1),
    )
    db.session.add(job)
    db.session.commit()

    en_body = client.get(f"/jobs/{job.id}").data.decode("utf-8")
    assert "Sep" in en_body

    client.post("/set-locale", data={"lang": "de", "next": f"/jobs/{job.id}"})
    de_body = client.get(f"/jobs/{job.id}").data.decode("utf-8")
    assert "01.09.2027" in de_body or "1.9.2027" in de_body


# ---------------------------------------------------------------------------
# Translation catalog staleness - same class of gap as the Tailwind CSS
# and migration-not-run incidents (DECISIONS.md/DEPLOYMENT.md): the
# committed .mo is a compiled artifact Railway's deploy never regenerates,
# so a .po edit with no matching `pybabel compile` run would silently ship
# translation content that's out of sync with what's actually committed.
# ---------------------------------------------------------------------------

def test_german_catalog_mo_is_not_stale(tmp_path):
    po_path = REPO_ROOT / "translations" / "de" / "LC_MESSAGES" / "messages.po"
    committed_mo_path = REPO_ROOT / "translations" / "de" / "LC_MESSAGES" / "messages.mo"
    assert po_path.exists()
    assert committed_mo_path.exists()

    scratch_dir = tmp_path / "translations"
    (scratch_dir / "de" / "LC_MESSAGES").mkdir(parents=True)
    (scratch_dir / "de" / "LC_MESSAGES" / "messages.po").write_bytes(po_path.read_bytes())

    subprocess.run(
        [sys.executable, "-m", "babel.messages.frontend", "compile", "-d", str(scratch_dir)],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
    )

    fresh_mo = (scratch_dir / "de" / "LC_MESSAGES" / "messages.mo").read_bytes()
    committed_mo = committed_mo_path.read_bytes()
    assert fresh_mo == committed_mo, (
        "translations/de/LC_MESSAGES/messages.mo is STALE - it doesn't match a fresh "
        "compile of the committed .po file. Run `pybabel compile -d translations` and "
        "commit the result. See DEPLOYMENT.md's Translations (i18n) section."
    )


def test_extraction_finds_no_untranslated_strings_beyond_the_committed_catalog(tmp_path):
    """Guards the OTHER half of staleness: a string wrapped in _()/_l() in a
    template/py file but never pulled into messages.pot/the .po file at
    all (someone forgot to re-run `pybabel extract`/`update`) - distinct
    from the .mo-compile check above.

    Both -k flags matter, not just one: `-k lazy_gettext` alone misses
    every WTForms field label/validator message, since this app always
    imports lazy_gettext under the alias `_l` and pybabel matches by the
    literal call-site identifier, not the import source - a real bug
    found by this exact test during i18n pass 2 (see DECISIONS.md)."""
    pot_scratch = tmp_path / "messages.pot"
    subprocess.run(
        [
            sys.executable, "-m", "babel.messages.frontend", "extract",
            "-F", "babel.cfg", "-k", "lazy_gettext", "-k", "_l", "-o", str(pot_scratch), ".",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
    )

    from babel.messages.pofile import read_po

    with open(pot_scratch, "rb") as f:
        fresh_msgids = {m.id for m in read_po(f) if m.id}
    po_path = REPO_ROOT / "translations" / "de" / "LC_MESSAGES" / "messages.po"
    with open(po_path, "rb") as f:
        catalog_msgids = {m.id for m in read_po(f) if m.id}

    missing = fresh_msgids - catalog_msgids
    assert not missing, (
        f"String(s) wrapped in _()/_l() but missing from translations/de/LC_MESSAGES/messages.po: "
        f"{missing}. Run `pybabel extract -F babel.cfg -k lazy_gettext -k _l -o messages.pot .` then "
        f"`pybabel update -i messages.pot -d translations -l de`, translate the new entries, "
        f"and `pybabel compile -d translations`. See DEPLOYMENT.md."
    )
