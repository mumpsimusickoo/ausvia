"""Screens pass 7 (Landing, 2026-08-28) - last screen in the inventory.
Covers: the dynamically-generated footer source list (enabled adapters
only, never the bundle's hardcoded three), the absence of privacy/imprint
links (deliberately omitted, not stubbed - see DECISIONS.md), the honest
value-block copy (fixed weights, real category order), the 8-station
decorative journey strip, the preview cards' plausible (not all-high)
scores, and the closing CTA's real access-code field posting straight to
the existing auth.register endpoint with no auth logic changed.

Widen pass (2026-08-28, same day): the hero rebuild (two-column, bundle
composition, old counterform staircase graphic removed entirely) and the
1600px max-w-content wide-screen layout, single-sourced in
tailwind.config.js.
"""
from tests.conftest import login


def test_landing_renders_for_logged_out_visitor(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Your path to Ausbildung." in resp.data
    assert b"Access code only" in resp.data


def test_logged_in_user_redirected_away_from_landing(client, db, make_user):
    make_user(email="already@example.com", password="Password123!")
    login(client, "already@example.com", "Password123!")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")


def test_footer_lists_only_enabled_configured_sources(client):
    # TestingConfig forces Adzuna's credentials to None (see
    # app/jobs/adapters/manager.py + config.py) - its trial never started
    # in the real dev environment either, so it's genuinely unconfigured,
    # not just admin-scoped like Jooble (see the dedicated test below for
    # why Jooble is absent even once configured).
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Bundesagentur für Arbeit" in body
    assert "Adzuna" not in body
    assert "Jooble" not in body
    assert "Source:" in body  # singular - exactly one source enabled


def test_footer_excludes_jooble_even_when_configured(client, app):
    # Jooble's lifetime request budget is reserved for the admin's own
    # account (ADMIN_ONLY_SOURCES, admin-only scoping pass, 2026-08-29) -
    # a logged-out visitor must never see it claimed as a searched source,
    # regardless of whether a real key is configured or the source is
    # enabled in JobSourceSetting.
    app.config["JOOBLE_API_KEY"] = "test-jooble-key"
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Bundesagentur für Arbeit" in body
    assert "Jooble" not in body


def test_footer_excludes_manual_import_as_a_source(client):
    # "manual" always has a JobSourceSetting row (so admins can see/toggle
    # it), but it's a user-driven one-URL-at-a-time import, not something
    # AUSVIA searches on a visitor's behalf - it must never appear in a
    # "we search these sources" claim.
    resp = client.get("/")
    assert b"Manual import" not in resp.data


def test_footer_source_list_updates_once_adzuna_is_configured_and_enabled(app, db):
    # Proves the list is genuinely generated from get_enabled_adapter_names(),
    # not hardcoded - configuring a second adapter AND enabling it changes
    # the rendered output without touching the template. Adzuna off-by-
    # default pass (2026-08-30): credentials alone are deliberately not
    # enough any more (see app/jobs/adapters/manager.py's
    # SEED_DISABLED_SOURCES) - this test used to configure credentials
    # only and rely on the old fail-open default, which was exactly the
    # bug that pass fixed. See the companion test right below for that
    # credentials-alone case.
    from app.models.job import JobSourceSetting

    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    with app.app_context():
        db.session.add(JobSourceSetting(source_name="adzuna", display_name="Adzuna", is_enabled=True))
        db.session.commit()
    client = app.test_client()
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Adzuna" in body
    assert "Sources:" in body  # plural - two sources now enabled


def test_footer_source_list_does_not_show_adzuna_from_credentials_alone(app, db):
    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    client = app.test_client()
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Adzuna" not in body


def test_footer_has_real_privacy_and_impressum_links(client):
    # Impressum/privacy pass (2026-08-31): real pages now exist (see
    # DECISIONS.md's 2026-08-28 entry for why they were deliberately
    # deferred until now, and this pass's own entry for the fix) - the
    # footer's links must point at the real routes, not a dead "#" or an
    # absent link.
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert 'href="/privacy"' in body
    assert 'href="/impressum"' in body


def test_value_blocks_state_fixed_weights_and_real_category_order(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "fixed weights" in body
    # Real weighting order from app/jobs/matching.py's match_band (30/25/20/15/10)
    idx_skills = body.index("Skills")
    idx_language = body.index("Language")
    idx_education = body.index("Education")
    idx_location = body.index("Location")
    idx_start = body.index("Start")
    assert idx_skills < idx_language < idx_education < idx_location < idx_start


def test_value_blocks_cover_the_three_real_constraints(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "never invented experience" in body
    assert "never invented company details" in body
    assert "you review and send them yourself" in body


def test_journey_strip_shows_all_eight_stages(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    for stage in ["Discover", "Match", "Prepare", "Apply", "Track", "Reply", "Interview", "Offer"]:
        assert stage in body


def test_preview_card_scores_are_not_all_high(client):
    # The page's own claim is that scoring is honest, not flattering - a
    # spread of bands (not three 90+ scores) is the point being verified.
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Strong match" in body
    assert "Good match" in body
    assert "Some gaps" in body


def test_closing_cta_posts_real_access_code_to_register(client, db):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert 'action="/auth/register"' in body
    assert 'name="access_code"' in body
    assert 'name="csrf_token"' in body


def test_closing_cta_code_field_carries_through_to_register_page(client, db):
    # Submitting only the code (as the landing form does) should land on
    # the real register page with the code retained and the still-missing
    # fields flagged - not silently discarded. No auth logic is exercised
    # differently than posting the full form would.
    resp = client.post(
        "/auth/register",
        data={"access_code": "ABCD-1234-EFGH"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"ABCD-1234-EFGH" in resp.data
    assert b"This field is required" in resp.data


def test_closing_cta_invalid_code_reaches_the_real_gate_once_fields_are_filled(client, db):
    # Two-step flow: landing hands off a bogus code, the visitor then fills
    # in the rest on the real register page - same rejection as posting
    # the whole form directly (tests/test_auth.py's own coverage).
    resp = client.post(
        "/auth/register",
        data={
            "access_code": "ZZZZ-ZZZZ-ZZZZ",
            "email": "nobody-landing@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "age_confirmed": "y",
        },
        follow_redirects=True,
    )
    assert b"Invalid access code" in resp.data


def test_old_counterform_hero_is_gone(client):
    # The pre-2.0 hero (centered single column, staircase SVG cutout,
    # "Five stages" caption) had no bundle equivalent and was removed
    # entirely by the widen pass, not hidden or relocated.
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Five stages" not in body
    assert "aspect-ratio: 1240 / 300" not in body
    assert "fill-rule" not in body


def test_hero_is_two_column_with_eyebrow_and_preview_panel(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "AUSBILDUNG · NATIONWIDE" in body
    # The preview panel now lives inside the hero - confirm it renders
    # exactly once, not once in the hero and once in a leftover standalone
    # section (the old section this pass folded into the hero).
    assert body.count("FIND AUSBILDUNG · LEIPZIG") == 1
    assert body.count("APPLICATION · HANSEATIK SYSTEME") == 1
    assert body.count("Ausbildung Mechatroniker/in (m/w/d)") == 1


def test_access_code_badge_and_how_it_works_link_moved_to_header(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    # Exactly one "Access code only" badge now (header, not the old hero).
    assert body.count("Access code only") == 1
    assert "See how it works" in body


def test_header_has_no_max_width_wrapper(client):
    # The header is deliberately full-width/edge-to-edge - every other
    # section uses max-w-content, but the header must not.
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    header_markup = body[body.index("<header"):body.index("</header>")]
    assert "max-w-content" not in header_markup
    assert "max-w-5xl" not in header_markup


def test_content_sections_use_the_single_sourced_wide_max_width(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    # Scoped to landing.html's own markup (from <header> on) - base.html's
    # shared pre-content flash-message wrapper still uses max-w-5xl and is
    # out of this pass's scope (it's shared chrome for every public page,
    # not landing-specific content).
    landing_markup = body[body.index("<header"):]
    assert "max-w-5xl" not in landing_markup  # fully migrated off the old, narrower container
    assert landing_markup.count("max-w-content") >= 5  # hero, journey strip, value blocks, closing CTA, footer


def test_theme_toggle_renders_exactly_once_in_the_header(client):
    # Toggle-fix pass, 2026-08-28: theme_toggle() was defined only inside
    # base.html's authenticated branch, so it was never actually reachable
    # from landing.html - confirmed via git history, not assumed. Moved to
    # _components.html as a real importable macro; this asserts the moved
    # macro renders on the public page, exactly once (not duplicated with
    # base.html's own authenticated-branch instances, which never render
    # for a logged-out visitor in the first place).
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    header_markup = body[body.index("<header"):body.index("</header>")]
    assert 'id="theme-toggle-landing"' in header_markup
    assert body.count('id="theme-toggle-') == 1


def test_theme_toggle_still_renders_on_authenticated_pages(client, db, make_user):
    # Regression check: moving theme_toggle() out of base.html's local
    # scope into an import must not break its two existing authenticated
    # call sites (mobile topbar, desktop sidebar header).
    make_user(email="toggle-regress@example.com", password="Password123!")
    login(client, "toggle-regress@example.com", "Password123!")
    resp = client.get("/dashboard")
    body = resp.data.decode("utf-8")
    assert 'id="theme-toggle-mobile"' in body
    assert 'id="theme-toggle-desktop"' in body
