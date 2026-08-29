"""Screens pass 3 (Dashboard, 2026-08-27). Covers: the follow-ups-due fix
(was hardcoded to 0), the "Next up" hero card's selection logic and its
empty-state variants (brand-new account vs. a healthy one with nothing
urgent), the applications table, and the cross-application insight's
gating/grounding. See DECISIONS.md for the staleness-dating and
grounding rationale.
"""
from datetime import date, timedelta

from app.ai import dashboard_insight
from app.ai.provider import AIProvider, AIResponse
from app.models.ai import DashboardInsight
from app.models.application import Application
from app.models.job import Company
from tests.conftest import login
from tests.test_applications import make_job


def make_company(db, name):
    company = Company(name=name, normalized_name=name.lower())
    db.session.add(company)
    db.session.commit()
    return company


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text
        self.call_count = 0

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        self.call_count += 1
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def test_follow_ups_due_counts_real_due_applications(client, db, make_user):
    user = make_user(email="dash1@example.com", password="Password123!")
    login(client, "dash1@example.com", "Password123!")

    job1 = make_job(db, dedup_key="dash-fu-1")
    job2 = make_job(db, dedup_key="dash-fu-2")
    job3 = make_job(db, dedup_key="dash-fu-3")
    db.session.add_all([
        Application(user_id=user.id, job_id=job1.id, status="follow_up", follow_up_date=date.today() - timedelta(days=1)),
        Application(user_id=user.id, job_id=job2.id, status="follow_up", follow_up_date=date.today() + timedelta(days=5)),
        Application(user_id=user.id, job_id=job3.id, status="sent", follow_up_date=None),
    ])
    db.session.commit()

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)
    assert "Follow-ups due" in html
    # exactly one of the three is actually due (past date) - was hardcoded
    # to "0" before this pass regardless of real data.
    idx = html.index("Follow-ups due")
    assert ">1<" in html[idx:idx + 400]


def test_hero_card_promotes_highest_priority_digest_item(client, db, make_user):
    user = make_user(email="dash2@example.com", password="Password123!")
    login(client, "dash2@example.com", "Password123!")

    ready_job = make_job(db, dedup_key="dash-hero-1", title="Ausbildung Ready Job")
    deadline_job = make_job(
        db, dedup_key="dash-hero-2", title="Ausbildung Deadline Job",
        application_deadline=date.today() + timedelta(days=3),
    )
    db.session.add_all([
        Application(user_id=user.id, job_id=ready_job.id, status="ready"),  # priority 50
        Application(user_id=user.id, job_id=deadline_job.id, status="preparing"),  # priority 80
    ])
    db.session.commit()

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)
    assert "NEXT UP" in html
    next_up_idx = html.index("NEXT UP")
    # the deadline item (higher priority) must be the one promoted, not the
    # ready-but-lower-priority one
    assert "Ausbildung Deadline Job" in html[next_up_idx:next_up_idx + 600]


def test_dashboard_brand_new_account_shows_written_empty_states(client, db, make_user):
    make_user(email="dash3@example.com", password="Password123!")
    login(client, "dash3@example.com", "Password123!")

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)
    assert "Nothing to show yet" in html
    assert "Nothing to prioritize yet" in html
    assert "No applications yet" in html
    assert "Search Ausbildung postings" in html


def test_dashboard_healthy_account_shows_calm_not_dashed_hero(client, db, make_user):
    """One application, nothing time-sensitive or stalled about it - the
    account has real activity, so this must read as "all good", not as the
    brand-new "nothing here yet" empty state."""
    user = make_user(email="dash4@example.com", password="Password123!")
    login(client, "dash4@example.com", "Password123!")
    job = make_job(db, dedup_key="dash-healthy-1")
    db.session.add(Application(user_id=user.id, job_id=job.id, status="sent"))
    db.session.commit()

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)
    assert "Nothing needs your attention right now." in html
    assert "All caught up" in html
    assert "Nothing to show yet" not in html


def test_applications_table_shows_status_and_relative_date(client, db, make_user):
    user = make_user(email="dash5@example.com", password="Password123!")
    login(client, "dash5@example.com", "Password123!")
    company = make_company(db, "Tablewerk GmbH")
    job = make_job(db, dedup_key="dash-table-1", title="Ausbildung Table Job", company_id=company.id)
    db.session.add(Application(user_id=user.id, job_id=job.id, status="interview"))
    db.session.commit()

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)
    assert "Ausbildung Table Job" in html
    assert "Tablewerk GmbH" in html
    assert "Interview" in html
    assert "today" in html


def test_cross_app_insight_hidden_below_minimum_applications(client, db, make_user):
    user = make_user(email="dash6@example.com", password="Password123!")
    login(client, "dash6@example.com", "Password123!")
    job = make_job(db, dedup_key="dash-insight-1")
    db.session.add(Application(user_id=user.id, job_id=job.id, status="sent"))
    db.session.commit()

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)
    assert "Add a second application" in html
    assert "Generate insight" not in html


def test_cross_app_insight_generate_offered_at_two_applications(client, db, make_user):
    user = make_user(email="dash7@example.com", password="Password123!")
    login(client, "dash7@example.com", "Password123!")
    job1 = make_job(db, dedup_key="dash-insight-2a")
    job2 = make_job(db, dedup_key="dash-insight-2b")
    db.session.add_all([
        Application(user_id=user.id, job_id=job1.id, status="sent"),
        Application(user_id=user.id, job_id=job2.id, status="sent"),
    ])
    db.session.commit()

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)
    assert "Generate insight" in html


def test_generate_insight_route_blocks_below_minimum(client, db, make_user):
    user = make_user(email="dash8@example.com", password="Password123!")
    login(client, "dash8@example.com", "Password123!")
    job = make_job(db, dedup_key="dash-insight-3")
    db.session.add(Application(user_id=user.id, job_id=job.id, status="sent"))
    db.session.commit()

    resp = client.post("/dashboard/insight", follow_redirects=True)
    assert b"Add at least two applications" in resp.data
    assert DashboardInsight.query.filter_by(user_id=user.id).first() is None


def test_generate_insight_route_mock_mode_is_honest(client, db, make_user):
    user = make_user(email="dash9@example.com", password="Password123!")
    login(client, "dash9@example.com", "Password123!")
    job1 = make_job(db, dedup_key="dash-insight-4a")
    job2 = make_job(db, dedup_key="dash-insight-4b")
    db.session.add_all([
        Application(user_id=user.id, job_id=job1.id, status="sent"),
        Application(user_id=user.id, job_id=job2.id, status="sent"),
    ])
    db.session.commit()

    resp = client.post("/dashboard/insight", follow_redirects=True)
    assert resp.status_code == 200
    insight = DashboardInsight.query.filter_by(user_id=user.id).first()
    assert insight is not None
    assert insight.provider == "mock"
    assert insight.reliability is None  # unpopulated by design - confirm badge hides
    html = resp.get_data(as_text=True)
    assert "aren&#39;t available" in html or "aren't available" in html
    assert "RELIABILITY" not in html


def test_generate_insight_route_uses_real_provider_and_regenerate_href(client, db, make_user, monkeypatch):
    user = make_user(email="dash10@example.com", password="Password123!")
    login(client, "dash10@example.com", "Password123!")
    job1 = make_job(db, dedup_key="dash-insight-5a")
    job2 = make_job(db, dedup_key="dash-insight-5b")
    db.session.add_all([
        Application(user_id=user.id, job_id=job1.id, status="sent"),
        Application(user_id=user.id, job_id=job2.id, status="sent"),
    ])
    db.session.commit()
    monkeypatch.setattr(dashboard_insight, "get_provider", lambda: FakeProvider("Both applications sit in electrical trades."))

    resp = client.post("/dashboard/insight", follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert "Both applications sit in electrical trades." in html
    assert "Regenerate" in html


def test_dashboard_insight_regenerates_when_ui_locale_changes(client, db, make_user, monkeypatch):
    """i18n pass 3 follow-up (2026-08-29): the cross-application insight
    was resolved into the "follows the UI language" bucket - genuinely
    candidate-facing content, rendered on the Dashboard via the same
    intelligence_surface() component company insight/profile coaching use
    (see DECISIONS.md). Same locale-cache-invalidation contract as
    test_match_routes.py's narrative test."""
    user = make_user(email="dash-locale@example.com", password="Password123!")
    login(client, "dash-locale@example.com", "Password123!")
    job1 = make_job(db, dedup_key="dash-insight-locale-a")
    job2 = make_job(db, dedup_key="dash-insight-locale-b")
    db.session.add_all([
        Application(user_id=user.id, job_id=job1.id, status="sent"),
        Application(user_id=user.id, job_id=job2.id, status="sent"),
    ])
    db.session.commit()

    provider = FakeProvider("Both applications sit in electrical trades.")
    monkeypatch.setattr(dashboard_insight, "get_provider", lambda: provider)

    client.post("/set-locale", data={"lang": "en", "next": "/dashboard"})
    resp = client.post("/dashboard/insight", follow_redirects=True)
    assert resp.status_code == 200
    assert provider.call_count == 1

    insight = DashboardInsight.query.filter_by(user_id=user.id).first()
    assert insight.generated_locale == "en"

    # Same locale again: cached, no new AI call.
    resp = client.post("/dashboard/insight", follow_redirects=True)
    assert resp.status_code == 200
    assert provider.call_count == 1

    # Locale switch: must regenerate, even though nothing about the
    # applications or profile changed.
    client.post("/set-locale", data={"lang": "de", "next": "/dashboard"})
    resp = client.post("/dashboard/insight", follow_redirects=True)
    assert resp.status_code == 200
    assert provider.call_count == 2

    db.session.refresh(insight)
    assert insight.generated_locale == "de"
