"""Tests for the public plans page (app/main/routes.py's plans(), plans
page + access expiry pass, 2026-08-30) and the landing page's new
"Request access" CTA. No payment gateway - every real assertion here is
about the numbers/links being correct, not about any billing flow.
"""
from urllib.parse import unquote

from app.plans import PLAN_MONTHLY_PRICES_DH, WHATSAPP_NUMBER, YEARLY_MULTIPLIER, whatsapp_plan_url
from tests.conftest import login


def test_plans_page_renders_for_logged_out_visitor(client):
    resp = client.get("/plans")
    assert resp.status_code == 200
    assert b"Simple, transparent pricing" in resp.data


def test_plans_page_redirects_authenticated_user_to_dashboard(client, db, make_user):
    make_user(email="planviewer@example.com", password="Password123!")
    login(client, "planviewer@example.com", "Password123!")
    resp = client.get("/plans", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")


def test_plans_page_shows_all_three_monthly_prices(client):
    resp = client.get("/plans")
    body = resp.data.decode("utf-8")
    for users, monthly_dh in PLAN_MONTHLY_PRICES_DH:
        assert f"{monthly_dh}" in body


def test_plans_page_yearly_prices_are_exactly_ten_times_monthly(client):
    # The stated rule: yearly = monthly x 10, not x12 (a deliberate
    # discount, not a rounding artifact) - checked against the rendered
    # page, not just the constant in app/plans.py.
    resp = client.get("/plans")
    body = resp.data.decode("utf-8")
    for users, monthly_dh in PLAN_MONTHLY_PRICES_DH:
        assert monthly_dh * YEARLY_MULTIPLIER == monthly_dh * 10
        assert f"{monthly_dh * 10}" in body


# --- WhatsApp link precision: six distinct combinations (1/2/5 users x
# monthly/yearly), each checked for its EXACT expected URL - not just
# "some substring naming a user count appears somewhere on the page",
# which could pass even if every card's link were wrong or identical,
# since "1-user" also appears in unrelated card copy (e.g. "1 USER",
# "1 simultaneous login"). ---

def test_whatsapp_plan_url_all_six_combinations_are_distinct():
    urls = {
        (users, yearly): whatsapp_plan_url(users, yearly=yearly)
        for users, _ in PLAN_MONTHLY_PRICES_DH
        for yearly in (False, True)
    }
    assert len(urls) == 6
    assert len(set(urls.values())) == 6  # no two combinations collide

    for (users, yearly), url in urls.items():
        assert url.startswith(f"https://wa.me/{WHATSAPP_NUMBER}?text=")
        decoded = unquote(url)
        assert f"{users}-user" in decoded
        assert ("yearly" if yearly else "monthly") in decoded
        # The OTHER period's word must not also appear (rules out a
        # template that concatenates both words instead of picking one).
        assert ("monthly" if yearly else "yearly") not in decoded


def test_plans_page_renders_all_six_exact_whatsapp_urls(client):
    resp = client.get("/plans")
    body = resp.data.decode("utf-8")
    for users, _monthly_dh in PLAN_MONTHLY_PRICES_DH:
        for yearly in (False, True):
            expected_url = whatsapp_plan_url(users, yearly=yearly)
            assert expected_url in body, (
                f"Expected the exact WhatsApp URL for users={users} yearly={yearly} "
                f"to appear verbatim in the rendered page: {expected_url}"
            )


def test_plans_page_no_two_rendered_whatsapp_urls_are_identical(client):
    import re

    resp = client.get("/plans")
    body = resp.data.decode("utf-8")
    hrefs = re.findall(r'href="(https://wa\.me/[^"]+)"', body)
    assert len(hrefs) == 6  # 3 cards x (monthly + yearly) each
    assert len(set(hrefs)) == 6


def test_landing_page_has_request_access_cta_linking_to_plans(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Request access" in body
    assert '/plans"' in body
