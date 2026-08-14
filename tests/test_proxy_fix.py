"""Regression tests for the Gmail OAuth redirect_uri bug: Railway (like
Heroku/Render) terminates TLS at its edge and forwards to this container
over plain HTTP internally, so without help, url_for(..., _external=True)
(gmail_oauth.py's _callback_url(), used as the OAuth redirect_uri) reports
http:// even though the site is genuinely served over https:// - Google's
OAuth flow rejects that redirect_uri outright (redirect_uri_mismatch). See
app/__init__.py's ProxyFix wiring for the fix and the reasoning on why it's
scoped to production only.
"""
import pytest

from app import create_app
from app.integrations import gmail_oauth


@pytest.fixture
def production_app(monkeypatch):
    from config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "test-only-production-secret")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/test_db")
    app = create_app()

    # Ad-hoc, test-only route: the only reliable way to inspect what
    # url_for(..., _external=True) produces once a request has gone all
    # the way through app.wsgi_app (ProxyFix included, since it wraps that
    # exact attribute) - unlike app.test_request_context(), which builds a
    # request context directly against the Flask app object and never
    # touches the wrapped wsgi_app/ProxyFix at all.
    @app.route("/__test_callback_url__")
    def _test_callback_url():
        return gmail_oauth._callback_url()

    return app


def test_callback_url_is_https_behind_proxy_with_forwarded_proto_header(production_app):
    """The actual bug and its fix: a realistic Railway-shaped request
    (X-Forwarded-Proto/-Host, matching what its edge proxy actually sends)
    must produce an https:// redirect_uri, not http://."""
    client = production_app.test_client()
    resp = client.get(
        "/__test_callback_url__",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "ausvia-production.up.railway.app",
        },
    )
    assert resp.get_data(as_text=True) == (
        "https://ausvia-production.up.railway.app/integrations/gmail/callback"
    )


def test_callback_url_reflects_the_header_not_a_hardcoded_scheme(production_app):
    """ProxyFix corrects the scheme based on what the header actually says -
    it doesn't just hardcode https for "production". No header present (not
    a scenario Railway ever produces, but worth pinning so this isn't
    mistaken for an unconditional https rewrite) means Flask still reports
    whatever it directly saw."""
    client = production_app.test_client()
    resp = client.get("/__test_callback_url__")
    assert resp.get_data(as_text=True).startswith("http://")


def test_forwarded_proto_header_is_ignored_outside_production(app, client):
    """Scoping check: the same header must do nothing outside production,
    where there's no real proxy in front of the app and nothing should
    trust a client-supplied X-Forwarded-* header. Also proves the
    production gate actually gates something, not just that it's a no-op
    everywhere."""

    @app.route("/__test_callback_url__")
    def _test_callback_url():
        return gmail_oauth._callback_url()

    resp = client.get(
        "/__test_callback_url__",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "ausvia-production.up.railway.app",
        },
    )
    body = resp.get_data(as_text=True)
    assert body.startswith("http://")
    assert "ausvia-production.up.railway.app" not in body
