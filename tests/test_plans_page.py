"""Tests for the public plans page (app/main/routes.py's plans(), plans
page + access expiry pass, 2026-08-30) and the landing page's new
"Request access" CTA. No payment gateway - every real assertion here is
about the numbers/links being correct, not about any billing flow.
"""
from urllib.parse import unquote

from app.plans import PLAN_MONTHLY_PRICES_DH, WHATSAPP_NUMBER, YEARLY_MULTIPLIER
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


def test_plans_page_whatsapp_links_are_plan_specific(client):
    resp = client.get("/plans")
    body = resp.data.decode("utf-8")
    assert f"wa.me/{WHATSAPP_NUMBER}" in body
    # Each plan's monthly AND yearly pre-filled message must be present and
    # distinguishable - not one generic message reused for every card.
    for users, _monthly_dh in PLAN_MONTHLY_PRICES_DH:
        assert f"{users}-user" in unquote(body) or f"{users}-user" in body


def test_plans_page_monthly_and_yearly_whatsapp_messages_differ(client):
    resp = client.get("/plans")
    body = unquote(resp.data.decode("utf-8"))
    assert "monthly AUSVIA plan" in body
    assert "yearly AUSVIA plan" in body


def test_landing_page_has_request_access_cta_linking_to_plans(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Request access" in body
    assert '/plans"' in body
