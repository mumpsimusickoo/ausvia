"""Route-level lifecycle tests for the job-description extraction pass:
confirms the real /jobs/<id> route actually chains enrich_job_detail() ->
extract_job_requirements() correctly (once per canonical Job, not per
view), that Adzuna/Jooble-sourced jobs are never affected (they have no
separate detail endpoint to enrich from in the first place), and that the
existing detail route keeps working end to end. submit_task() runs
synchronously under TESTING (see app/tasks/runner.py), so these can
assert on results directly after a single client.get() call.
"""
import app.ai.job_requirements_extraction as extraction_module
from app.ai.provider import AIProvider, AIResponse
from app.jobs.adapters import manager as adapter_manager
from app.jobs.adapters.base import NormalizedJob
from app.jobs.dedupe import find_or_create_canonical_job
from app.models.job import Job
from tests.conftest import login

RAW_SEARCH_RESULT = {
    "referenznummer": "AA-EXTRACT-1",
    "stellenangebotsTitel": "Ausbildung Mechatroniker (m/w/d)",
    "firma": "TestFirma GmbH",
    "stellenlokationen": [{"adresse": {"ort": "Stuttgart"}}],
    "externeURL": "https://example.com/job/extract-1",
}
DETAIL_RESPONSE = {
    "stellenangebotsBeschreibung": (
        "Das bringst Du mit:\n- Sehr gute Deutschkenntnisse in Wort und Schrift\n"
        "Das erwartet Dich:\n- SPS-Programmierung"
    ),
}


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name)


def make_arbeitsagentur_job(db):
    adapter = adapter_manager.ADAPTERS["arbeitsagentur"]
    normalized = adapter.normalize(RAW_SEARCH_RESULT)
    job, _ = find_or_create_canonical_job(normalized)
    return job


def test_detail_route_chains_description_enrichment_and_extraction(client, db, make_user, monkeypatch):
    make_user(email="life1@example.com", password="Password123!")
    login(client, "life1@example.com", "Password123!")
    job = make_arbeitsagentur_job(db)

    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", lambda external_id: DETAIL_RESPONSE)
    fake = FakeProvider('{"skills": ["Deutschkenntnisse"], "languages": ["Deutsch"]}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200

    db.session.refresh(job)
    assert job.description is not None
    assert job.skills == ["Deutschkenntnisse"]
    # The curriculum-only mention must not have been extracted, even
    # though it's real text elsewhere in the same description.
    assert "SPS-Programmierung" not in job.skills


def test_extraction_runs_once_across_repeated_detail_views(client, db, make_user, monkeypatch):
    make_user(email="life2@example.com", password="Password123!")
    login(client, "life2@example.com", "Password123!")
    job = make_arbeitsagentur_job(db)

    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", lambda external_id: DETAIL_RESPONSE)
    calls = []

    def fake_get_provider():
        calls.append(1)
        return FakeProvider('{"skills": ["Deutschkenntnisse"], "languages": []}')

    monkeypatch.setattr(extraction_module, "get_provider", fake_get_provider)

    client.get(f"/jobs/{job.id}")
    client.get(f"/jobs/{job.id}")
    client.get(f"/jobs/{job.id}")

    assert len(calls) == 1


def test_adzuna_sourced_job_never_triggers_extraction(client, db, make_user, monkeypatch):
    make_user(email="life3@example.com", password="Password123!")
    login(client, "life3@example.com", "Password123!")

    normalized = NormalizedJob(
        source="adzuna", external_id="AZ-1", title="Ausbildung Elektroniker",
        company_name="Firma X", description=None, application_url="https://example.com/az/1",
    )
    job, _ = find_or_create_canonical_job(normalized)

    calls = []
    monkeypatch.setattr(extraction_module, "get_provider", lambda: calls.append(1) or FakeProvider("{}"))

    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200
    assert calls == []  # extraction was never even scheduled
    db.session.refresh(job)
    assert job.skills is None


def test_manual_job_never_triggers_extraction(client, db, make_user, monkeypatch):
    make_user(email="life4@example.com", password="Password123!")
    login(client, "life4@example.com", "Password123!")

    normalized = NormalizedJob(source="manual", title="Bäcker", company_name="Beispiel GmbH")
    job, _ = find_or_create_canonical_job(normalized)

    calls = []
    monkeypatch.setattr(extraction_module, "get_provider", lambda: calls.append(1) or FakeProvider("{}"))

    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200
    assert calls == []


def test_detail_route_still_functions_when_description_already_present(client, db, make_user, monkeypatch):
    # A job that never needs enrich_job_detail() to do anything (already
    # has a description) must still render normally, and must not
    # spuriously trigger extraction either - enrich_job_detail() returns
    # False, so nothing should be scheduled.
    make_user(email="life5@example.com", password="Password123!")
    login(client, "life5@example.com", "Password123!")
    job = Job(title="Elektroniker", dedup_key="life-existing", description="Already has a description.")
    db.session.add(job)
    db.session.commit()

    calls = []
    monkeypatch.setattr(extraction_module, "get_provider", lambda: calls.append(1) or FakeProvider("{}"))

    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200
    assert calls == []
