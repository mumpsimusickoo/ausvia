"""Phase 8 security audit (2.2): security response headers.

Manual after_request hook rather than Flask-Talisman - this project
deliberately keeps its dependency footprint minimal (no broker, no ORM
beyond SQLAlchemy+SQLite; see ARCHITECTURE.md/DECISIONS.md), and a manual
hook gives precise, readable control over the CSP.

CSP specifics and why:
- script-src is 'self' plus a per-request nonce for the app's inline
  <script> blocks: base.html's no-flash theme script and mobile-nav
  drawer/theme-toggle scripts, jobs/import.html's bookmarklet-drag hint,
  and jobs/import_bookmarklet.html's client-side form-prefill script (see
  app/jobs/routes.py's _bookmarklet_href()). Every inline <script> in
  app/templates/ carries nonce="{{ csp_nonce }}" for exactly this reason -
  grep for `<script` before adding a new one and forgetting it, or it'll be
  silently blocked by this CSP with no visible error to the user. No CDN
  script URL needed here since the Tailwind build pass (2026-08-26, see
  DECISIONS.md) - Tailwind is a compiled, committed static file now, not a
  runtime CDN script.
- style-src has no 'unsafe-inline' and needs none: that allowance existed
  only because the Tailwind CDN script injected its own <style> tag into
  the page at runtime, which nothing in this app's code could nonce. Once
  the CDN was replaced with a static, build-time <link rel="stylesheet">
  (Tailwind build pass, 2026-08-26 - see DECISIONS.md), that injection
  vector is gone, so style-src is locked down to 'self' plus Google Fonts'
  stylesheet host with no inline allowance at all.
- style-src-attr carries 'unsafe-inline' separately, narrower than the old
  blanket allowance: several templates set inline style="" attributes for
  values that are genuinely per-request data, not fixed design tokens
  (e.g. a computed match-score percentage as a bar width, a station
  connector's pixel height) - these can't be pre-baked into the compiled
  stylesheet as static classes. CSP Level 3's style-src-attr governs only
  inline style ATTRIBUTES, separately from style-src's own governance of
  <style> elements and <link> stylesheets - so this scopes the remaining
  inline-style allowance down to exactly the attack surface that still
  needs it (an attacker-controlled style ATTRIBUTE value), while the
  broader vector the CDN represented (an entire injected stylesheet) stays
  closed. Supported by all evergreen browsers (Chrome 111+, Firefox 102+,
  Safari 15.4+, all long-superseded by 2026); a browser that doesn't
  recognize style-src-attr ignores it and falls back to style-src alone for
  attribute checks too, which would then block those inline style
  attributes - an intentional fail-closed choice (missing/broken styling on
  a handful of very old browsers) over fail-open (silently re-widening
  style-src's own 'unsafe-inline').
- connect-src/form-action are 'self' only - grepped templates for fetch(),
  XMLHttpRequest, and external form actions; none exist, so nothing to
  allowlist beyond same-origin. One narrow, temporary exception: the
  Arbeitsagentur CORS diagnostic route (app/main/routes.py,
  DIAGNOSTIC_CORS_TEST_PATH below) needs connect-src to permit
  rest.arbeitsagentur.de specifically, or the browser would block its
  fetch() on our own CSP before ever testing Arbeitsagentur's CORS policy -
  a false negative that would look identical to a real CORS block. Scoped
  to that one path only; remove this carve-out along with the route once
  the diagnostic is no longer needed.
"""
import secrets

from flask import g, request

# Kept as a constant (rather than hardcoded inline below) so the route and
# this CSP carve-out can't drift out of sync if one changes without the other.
DIAGNOSTIC_CORS_TEST_PATH = "/diagnostics/arbeitsagentur-cors-test"


def init_security_headers(app):
    @app.before_request
    def _set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _inject_csp_nonce():
        return {"csp_nonce": g.get("csp_nonce", "")}

    @app.after_request
    def _set_security_headers(response):
        nonce = g.get("csp_nonce", "")
        connect_src = "'self'"
        if request.path == DIAGNOSTIC_CORS_TEST_PATH:
            connect_src += " https://rest.arbeitsagentur.de"
        csp = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "style-src-attr 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            f"connect-src {connect_src}; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "object-src 'none'"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Redundant with frame-ancestors 'none' above on modern browsers, but
        # cheap and covers older ones that only understand this header.
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Browsers only honor HSTS on a response actually received over
        # HTTPS, so sending it unconditionally (including over plain HTTP in
        # dev) is inert there and correct once behind real TLS in production.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
