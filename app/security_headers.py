"""Phase 8 security audit (2.2): security response headers.

Manual after_request hook rather than Flask-Talisman - this project
deliberately keeps its dependency footprint minimal (no build step, no
broker, no ORM beyond SQLAlchemy+SQLite; see ARCHITECTURE.md/DECISIONS.md),
and a manual hook gives precise, readable control over the one genuinely
tricky part here: the CSP has to coexist with loading Tailwind and Google
Fonts from CDNs at runtime (base.html), or it breaks every page's styling.

CSP specifics and why:
- script-src allows the Tailwind CDN script by URL, plus a per-request nonce
  for the app's own two inline <script> blocks (both in base.html - the
  tailwind.config block and the mobile-nav drawer toggle). No other template
  has an inline script (grepped for `<script` across app/templates/). This
  keeps script-src meaningfully restrictive - an injected inline script
  elsewhere on the page still won't execute.
- style-src needs 'unsafe-inline' unavoidably: the Tailwind CDN script
  compiles utility classes at runtime and injects its own <style> tag via
  JS, which is not something this app's code can attach a nonce to - it's
  internal to the CDN script's behavior. Nonce-ing this app's own static
  inline <style> block (also in base.html) wouldn't change that, so 'unsafe-
  inline' is the honest floor for style-src as long as the Tailwind CDN is
  in use. See DECISIONS.md/QA_REPORT.md for the separate "stop depending on
  the Tailwind CDN at runtime" finding this implies - not fixed here, that's
  a real build-step infrastructure change, not a header tweak.
- connect-src/form-action are 'self' only - grepped templates for fetch(),
  XMLHttpRequest, and external form actions; none exist, so nothing to
  allowlist beyond same-origin.
"""
import secrets

from flask import g


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
        csp = (
            "default-src 'self'; "
            f"script-src 'self' https://cdn.tailwindcss.com 'nonce-{nonce}'; "
            "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
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
