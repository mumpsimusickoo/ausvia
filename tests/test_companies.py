from app.companies import insights
from app.ai.provider import AIProvider, AIResponse
from app.models import Job
from app.models.job import Company
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
