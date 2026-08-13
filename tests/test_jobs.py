from app.jobs.adapters import manager as adapter_manager
from app.jobs.manual_import import FetchFailed
from app.models.job import Job, SavedJob, JobSourceSetting
from tests.conftest import login

SAMPLE_RAW_JOB = {
    "refnr": "AA-TEST-1",
    "titel": "Elektroniker für Automatisierungstechnik (m/w/d)",
    "arbeitgeber": "TestFirma GmbH",
    "arbeitsort": {"ort": "Stuttgart"},
    "aktuelleVeroeffentlichungsdatum": "2026-01-01",
    "externeUrl": "https://example.com/job/1",
}


def test_manual_import_save_creates_job(client, db, make_user):
    make_user(email="importer@example.com", password="Password123!")
    login(client, "importer@example.com", "Password123!")

    resp = client.post(
        "/jobs/import/save",
        data={
            "title": "Elektroniker für Automatisierungstechnik",
            "company_name": "Beispiel GmbH",
            "location": "Hamburg",
            "start_date": "2027",
            "application_url": "https://example.com/apply",
            "description": "Some job text.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    job = Job.query.filter_by(title="Elektroniker für Automatisierungstechnik").first()
    assert job is not None
    assert job.company_name == "Beispiel GmbH"
    assert job.listings[0].source == "manual"


def test_manual_import_requires_title_and_company(client, db, make_user):
    make_user(email="importer2@example.com", password="Password123!")
    login(client, "importer2@example.com", "Password123!")

    resp = client.post("/jobs/import/save", data={"title": "", "company_name": ""}, follow_redirects=True)
    assert b"Please fill in" in resp.data
    assert Job.query.count() == 0


def test_import_fetch_handles_blocked_site_gracefully(client, db, make_user, monkeypatch):
    make_user(email="importer3@example.com", password="Password123!")
    login(client, "importer3@example.com", "Password123!")

    def fake_fetch(url):
        raise FetchFailed("That site declined the request.")

    monkeypatch.setattr("app.jobs.routes.fetch_and_extract_text", fake_fetch)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://blocked-example.test/job/1"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"declined the request" in resp.data
    # should still render the review form so the user can paste text manually
    assert b"company_name" in resp.data


def test_search_ingests_via_mocked_adapter_and_persists(client, db, make_user, monkeypatch):
    make_user(email="searcher@example.com", password="Password123!")
    login(client, "searcher@example.com", "Password123!")

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "search", lambda keywords, location=None, **kw: [SAMPLE_RAW_JOB]
    )

    resp = client.get("/jobs/?keywords=Elektroniker")
    assert resp.status_code == 200
    assert b"TestFirma" in resp.data
    assert Job.query.count() == 1


def test_disabled_source_is_not_queried(app, db, client, make_user, monkeypatch):
    make_user(email="searcher2@example.com", password="Password123!")
    login(client, "searcher2@example.com", "Password123!")

    adapter_manager.ensure_source_settings_seeded()
    setting = JobSourceSetting.query.filter_by(source_name="arbeitsagentur").first()
    setting.is_enabled = False
    db.session.commit()

    calls = []
    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"],
        "search",
        lambda keywords, location=None, **kw: calls.append(1) or [SAMPLE_RAW_JOB],
    )

    client.get("/jobs/?keywords=Elektroniker")
    assert calls == []
    assert Job.query.count() == 0


def test_save_and_unsave_job(client, db, make_user):
    make_user(email="saver@example.com", password="Password123!")
    login(client, "saver@example.com", "Password123!")

    client.post(
        "/jobs/import/save",
        data={"title": "Mechatroniker", "company_name": "Firma X", "location": "Köln"},
    )
    job = Job.query.filter_by(title="Mechatroniker").first()

    resp = client.post(f"/jobs/{job.id}/save", follow_redirects=True)
    assert resp.status_code == 200
    assert SavedJob.query.count() == 1

    resp = client.get("/jobs/saved")
    assert b"Mechatroniker" in resp.data

    resp = client.post(f"/jobs/{job.id}/unsave", follow_redirects=True)
    assert resp.status_code == 200
    assert SavedJob.query.count() == 0


def test_saved_jobs_are_per_user(client, db, make_user):
    owner = make_user(email="jobowner@example.com", password="Password123!")
    other = make_user(email="jobother@example.com", password="Password123!")

    login(client, "jobowner@example.com", "Password123!")
    client.post("/jobs/import/save", data={"title": "Fachinformatiker", "company_name": "Firma Y"})
    job = Job.query.filter_by(title="Fachinformatiker").first()
    client.post(f"/jobs/{job.id}/save")
    client.get("/auth/logout")

    login(client, "jobother@example.com", "Password123!")
    resp = client.get("/jobs/saved")
    assert b"Fachinformatiker" not in resp.data


def test_job_detail_requires_login(client, db):
    resp = client.get("/jobs/1", follow_redirects=True)
    assert b"Log in" in resp.data
