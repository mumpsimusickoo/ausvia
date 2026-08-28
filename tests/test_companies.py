from datetime import date, timedelta

from app.companies import insights
from app.ai.provider import AIProvider, AIResponse
from app.models import Job
from app.models.application import Application
from app.models.job import Company, JobListing
from app.models.ai import CompanyInsight
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def make_company_with_job(db, description=None):
    company = Company(
        name="Siemens AG", normalized_name="siemensag", industry="Industrial automation",
        location="Stuttgart", website="https://siemens.com", description=description,
    )
    db.session.add(company)
    db.session.commit()
    job = Job(company_id=company.id, title="Elektroniker für Automatisierungstechnik", dedup_key="company-test-job")
    db.session.add(job)
    db.session.commit()
    return company, job


def test_company_detail_shows_real_fields_and_jobs(client, db, make_user):
    make_user(email="c1@example.com", password="Password123!")
    login(client, "c1@example.com", "Password123!")
    company, job = make_company_with_job(db, description="A real employer offering Ausbildung positions.")

    resp = client.get(f"/companies/{company.id}")
    assert resp.status_code == 200
    assert b"Siemens AG" in resp.data
    assert b"Industrial automation" in resp.data
    assert b"Stuttgart" in resp.data
    assert b"A real employer offering Ausbildung positions." in resp.data
    assert b"Elektroniker f\xc3\xbcr Automatisierungstechnik" in resp.data


def test_company_detail_without_description_is_honest_not_invented(client, db, make_user):
    make_user(email="c2@example.com", password="Password123!")
    login(client, "c2@example.com", "Password123!")
    company, job = make_company_with_job(db, description=None)

    resp = client.get(f"/companies/{company.id}")
    assert b"No verified description on file yet" in resp.data
    assert b"nothing is invented" in resp.data


def test_generate_insight_mock_mode_is_honest(client, db, make_user):
    make_user(email="c3@example.com", password="Password123!")
    login(client, "c3@example.com", "Password123!")
    company, job = make_company_with_job(db)

    resp = client.post(f"/companies/{company.id}/generate-insight", follow_redirects=True)
    assert resp.status_code == 200
    assert b"aren&#39;t available" in resp.data or b"aren't available" in resp.data

    insight = CompanyInsight.query.filter_by(company_id=company.id).first()
    assert insight is not None
    assert insight.provider == "mock"


def test_generate_insight_uses_real_provider_and_caches(app, db, make_user, monkeypatch):
    user = make_user(email="c4@example.com")
    company, job = make_company_with_job(db, description="Makes industrial automation equipment.")

    monkeypatch.setattr(insights, "get_provider", lambda: FakeProvider("A grounded fit summary."))

    insight1 = insights.generate_company_insight(user, company, [job])
    assert insight1.summary_text == "A grounded fit summary."
    assert insight1.provider == "fake"

    # calling again without a profile change should return the cached row,
    # not call the provider a second time (mirrors JobMatch's staleness rule)
    monkeypatch.setattr(insights, "get_provider", lambda: FakeProvider("A different summary."))
    insight2 = insights.generate_company_insight(user, company, [job])
    assert insight2.summary_text == "A grounded fit summary."

    assert CompanyInsight.query.filter_by(user_id=user.id, company_id=company.id).count() == 1


def test_company_insight_is_per_user_not_shared(app, db, make_user, monkeypatch):
    user1 = make_user(email="c5a@example.com")
    user2 = make_user(email="c5b@example.com")
    company, job = make_company_with_job(db)

    monkeypatch.setattr(insights, "get_provider", lambda: FakeProvider("Summary for user 1."))
    insights.generate_company_insight(user1, company, [job])

    assert insights.get_company_insight(user2, company) is None


def test_grounding_note_shown_under_about(client, db, make_user):
    make_user(email="c6@example.com", password="Password123!")
    login(client, "c6@example.com", "Password123!")
    company, job = make_company_with_job(db, description="Real description from a posting.")

    resp = client.get(f"/companies/{company.id}")
    assert b"no external database, nothing added" in resp.data


def test_facts_panel_states_why_fields_stay_blank(client, db, make_user):
    # Screens pass 6 (Company Detail, 2026-08-28): the honest-blank note is
    # the point of this screen's facts panel - most products would either
    # drop these fields silently or estimate them.
    make_user(email="c7@example.com", password="Password123!")
    login(client, "c7@example.com", "Password123!")
    company, job = make_company_with_job(db)

    resp = client.get(f"/companies/{company.id}")
    assert b"Employee count, founding year, and revenue aren" in resp.data
    assert b"stay blank rather than being estimated" in resp.data


def test_listings_on_file_counts_raw_listings_not_positions(client, db, make_user):
    # Deliberately the raw JobListing count, not len(jobs) - a company
    # with one canonical position merged from two source listings shows
    # 2 listings, not 1, the same duplicates-are-honest-signal reasoning
    # as Find Ausbildung's "N duplicates merged" line.
    make_user(email="c8@example.com", password="Password123!")
    login(client, "c8@example.com", "Password123!")
    company, job = make_company_with_job(db)
    db.session.add(JobListing(job_id=job.id, source="arbeitsagentur", external_id="c8-ext-1"))
    db.session.add(JobListing(job_id=job.id, source="adzuna", external_id="c8-ext-2"))
    db.session.commit()

    resp = client.get(f"/companies/{company.id}")
    html = resp.get_data(as_text=True)
    assert "Listings on file" in html
    # exactly one position, but two listings behind it
    assert html.count("Ausbildung positions at") == 1
    idx = html.index("Listings on file")
    assert ">2<" in html[idx:idx + 200]


def test_first_seen_is_earliest_job_discovered_at(client, db, make_user):
    make_user(email="c9@example.com", password="Password123!")
    login(client, "c9@example.com", "Password123!")
    company, job1 = make_company_with_job(db)
    job1.discovered_at = date.today() - timedelta(days=3)
    job2 = Job(
        company_id=company.id, title="Ausbildung Elektroniker/in",
        dedup_key="company-test-job-2", discovered_at=date.today() - timedelta(days=30),
    )
    db.session.add(job2)
    db.session.commit()

    resp = client.get(f"/companies/{company.id}")
    html = resp.get_data(as_text=True)
    # i18n pass 2: format_local_date() (English default locale in tests),
    # not a hardcoded %d.%m.%Y - see DECISIONS.md's mass date-formatting
    # sweep.
    from app.i18n import format_local_date

    with client.application.test_request_context("/"):
        expected = format_local_date(date.today() - timedelta(days=30))
    assert expected in html


def test_position_scores_shown_using_batched_matcher(client, db, make_user):
    user = make_user(email="c10@example.com", password="Password123!")
    login(client, "c10@example.com", "Password123!")
    from app.models.profile import Skill

    db.session.add(Skill(profile_id=user.profile.id, name="SPS", proficiency="advanced"))
    db.session.commit()
    company, job = make_company_with_job(db)
    job.skills = ["SPS"]
    db.session.commit()

    resp = client.get(f"/companies/{company.id}")
    assert b"Strong match" in resp.data


def test_your_application_here_shown_when_application_exists(client, db, make_user):
    user = make_user(email="c11@example.com", password="Password123!")
    login(client, "c11@example.com", "Password123!")
    company, job = make_company_with_job(db)
    db.session.add(Application(user_id=user.id, job_id=job.id, status="ready"))
    db.session.commit()

    resp = client.get(f"/companies/{company.id}")
    assert b"YOUR APPLICATION HERE" in resp.data
    assert b"Open application" in resp.data


def test_your_application_here_absent_when_no_application(client, db, make_user):
    make_user(email="c12@example.com", password="Password123!")
    login(client, "c12@example.com", "Password123!")
    company, job = make_company_with_job(db)

    resp = client.get(f"/companies/{company.id}")
    assert b"YOUR APPLICATION HERE" not in resp.data
    assert b"Open application" not in resp.data


def test_blank_profile_never_shows_a_fabricated_position_score(client, db, make_user):
    # Same bug class found and fixed in the Find Ausbildung pass: a wholly
    # blank profile (no skills/languages/education/preference) can still
    # make compute_match() return a positive score via
    # _score_location()'s "no preference = open to anywhere" default.
    # Company Detail's position list must not repeat it.
    make_user(email="c14@example.com", password="Password123!")
    login(client, "c14@example.com", "Password123!")
    company, job = make_company_with_job(db)  # no skills on the job either

    resp = client.get(f"/companies/{company.id}")
    html = resp.get_data(as_text=True)
    assert "Not scored" in html
    assert "Strong match" not in html


def test_multiple_open_positions_each_shown(client, db, make_user):
    make_user(email="c13@example.com", password="Password123!")
    login(client, "c13@example.com", "Password123!")
    company, job1 = make_company_with_job(db)
    job2 = Job(company_id=company.id, title="Ausbildung Elektroniker/in", dedup_key="company-test-job-multi-2")
    job3 = Job(company_id=company.id, title="Ausbildung Mechatroniker/in", dedup_key="company-test-job-multi-3")
    db.session.add_all([job2, job3])
    db.session.commit()

    resp = client.get(f"/companies/{company.id}")
    html = resp.get_data(as_text=True)
    assert "3 &middot;" in html or "3 ·" in html
    assert job1.title in html
    assert "Ausbildung Elektroniker/in" in html
    assert "Ausbildung Mechatroniker/in" in html
