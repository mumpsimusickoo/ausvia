"""Regression tests for Phase 8 security audit "Fix now" items.

D1: InvitationCode.generate_code() used stdlib random (not cryptographically
secure) despite SECURITY.md documenting secrets-backed generation.

2.1: create_app() silently fell back to DevelopmentConfig (DEBUG=True + an
insecure hardcoded SECRET_KEY) for any *unrecognized* FLASK_ENV value, not
just an unset one - a typo in a real deployment's env config would silently
run in dev mode. ProductionConfig also didn't force SESSION_COOKIE_SECURE/
REMEMBER_COOKIE_SECURE, relying on an env var that could be forgotten, and
a production deployment with no SECRET_KEY set would only fail deep inside
the first request that touched the session rather than at startup.

2.2: no security response headers existed anywhere (no CSP, X-Frame-Options,
X-Content-Type-Options, Referrer-Policy, or HSTS). Live-verified separately
(not by pytest, which has no browser) via Chrome DevTools Protocol that the
CSP doesn't break Tailwind/Google Fonts CDN loading or the mobile-nav
drawer's nonce'd inline script, and produces zero browser console CSP
violations - these tests only check the headers/nonce plumbing itself.
"""
import re

import pytest

from app import create_app
from app.models.access_code import generate_code


def test_generate_code_uses_secrets_module_not_random():
    import app.models.access_code as access_code_module

    assert not hasattr(access_code_module, "random"), (
        "access_code.py should no longer import the non-cryptographic random module"
    )
    assert "secrets" in dir(access_code_module)


def test_generate_code_still_produces_the_expected_shape():
    code = generate_code()
    assert re.match(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$", code)
    for excluded in "01OI":
        assert excluded not in code


def test_unset_flask_env_defaults_to_development_without_error(monkeypatch):
    monkeypatch.delenv("FLASK_ENV", raising=False)
    app = create_app()
    assert app.config["DEBUG"] is True


def test_unrecognized_flask_env_raises_instead_of_silently_defaulting(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "produciton")  # deliberate typo
    with pytest.raises(RuntimeError, match="Unrecognized FLASK_ENV"):
        create_app()


def test_production_without_secret_key_raises_at_startup(monkeypatch):
    # Same import-time-vs-call-time issue as the cookie test below: patch the
    # already-loaded class attribute directly rather than the env var, so this
    # doesn't depend on whether the real process environment happens to have
    # SECRET_KEY set or not.
    from config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", None)
    monkeypatch.setenv("FLASK_ENV", "production")
    with pytest.raises(RuntimeError, match="SECRET_KEY is not set"):
        create_app()


def test_production_without_database_url_raises_at_startup(monkeypatch):
    # Deployment readiness pass: DATABASE_URL always has *some* resolved
    # value (config.py falls back to local SQLite), so this has to check the
    # raw env var directly rather than app.config - see app/__init__.py.
    from config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "test-only-production-secret")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        create_app()


def test_production_config_forces_secure_cookies(monkeypatch):
    # config.py's Config.SECRET_KEY (and friends) are read from the environment
    # at *module import time*, not at create_app() call time - by the time this
    # test runs, config.py is already imported, so monkeypatching the env var
    # here wouldn't reach it. Patch the already-loaded class attribute instead,
    # which is the thing create_app() actually reads.
    from config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "test-only-production-secret")
    monkeypatch.setenv("FLASK_ENV", "production")
    # Deployment readiness pass: production also now fails loudly without a
    # real DATABASE_URL (see app/__init__.py) - set one here so this test
    # keeps exercising the cookie/DEBUG assertions it's actually about.
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/test_db")
    app = create_app()
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True
    assert app.config["DEBUG"] is False


def test_security_headers_present_on_every_response(client):
    resp = client.get("/")
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in resp.headers["Strict-Transport-Security"]


def test_csp_allows_fonts_but_nothing_broader(client):
    # Tailwind build pass, 2026-08-26: the CDN script is gone - Tailwind is
    # a compiled, committed static file now (app/static/css/tailwind.css),
    # so script-src no longer needs to allowlist cdn.tailwindcss.com, and
    # style-src no longer needs 'unsafe-inline' (that only existed for the
    # CDN's runtime-injected <style> tag). See DECISIONS.md.
    resp = client.get("/")
    csp = resp.headers["Content-Security-Policy"]
    assert "https://cdn.tailwindcss.com" not in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_style_src_has_no_unsafe_inline_but_style_src_attr_does(client):
    # style-src governs <style> elements and <link rel="stylesheet"> - no
    # inline allowance needed since Tailwind stopped injecting its own
    # <style> tag at runtime. style-src-attr governs inline style="..."
    # attributes specifically (CSP Level 3) - several templates set
    # per-request computed values there (a match-score bar width, etc.)
    # that can't be pre-baked into the compiled stylesheet as static
    # classes, so that narrower allowance stays. See
    # app/security_headers.py's module docstring for the full reasoning.
    resp = client.get("/")
    csp = resp.headers["Content-Security-Policy"]
    style_src = [d for d in csp.split("; ") if d.startswith("style-src ")][0]
    assert "'unsafe-inline'" not in style_src
    assert "style-src-attr 'unsafe-inline'" in csp


def test_csp_nonce_is_unique_per_request_and_appears_in_rendered_page(client):
    resp1 = client.get("/")
    resp2 = client.get("/")
    csp1 = resp1.headers["Content-Security-Policy"]
    csp2 = resp2.headers["Content-Security-Policy"]
    nonce1 = csp1.split("'nonce-")[1].split("'")[0]
    nonce2 = csp2.split("'nonce-")[1].split("'")[0]

    assert nonce1 != nonce2, "each response should get a fresh nonce"
    assert f'nonce="{nonce1}"'.encode() in resp1.data
    assert f'nonce="{nonce2}"'.encode() in resp2.data
