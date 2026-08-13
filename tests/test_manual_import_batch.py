"""Tests for the bulk manual-import flow (multiple URLs pasted at once,
reviewed and saved one at a time) and the bookmarklet prefill path -
app/jobs/routes.py, app/models/manual_import.py.
"""
from app.jobs.manual_import import FetchFailed
from app.models import Job, ManualImportBatch, User
from app.models.access_code import generate_code
from tests.conftest import login


def fake_fetch_factory(results):
    """results: {url: "some title text"} for success, or {url: FetchFailed("...")} for failure."""
    def _fake(url):
        outcome = results.get(url)
        if isinstance(outcome, Exception):
            raise outcome
        return {"page_title": outcome or f"Title for {url}", "text": f"Body text for {url}. " * 5}
    return _fake


def make_logged_in_user(db, client, make_user, email="batchuser@example.com"):
    make_user(email=email, password="Password123!")
    login(client, email, "Password123!")
    return User.query.filter_by(email=email).first()


# --- basic batch fetch ---------------------------------------------------

def test_bulk_fetch_all_succeed_creates_batch_and_shows_first_item(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://b.test/2": "Job B"}),
    )

    resp = client.post(
        "/jobs/import/fetch",
        data={"urls": "https://a.test/1\nhttps://b.test/2"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Fetched 2 of 2" in resp.data
    assert b"Reviewing 1 of 2" in resp.data
    assert b"Job A" in resp.data  # first item's title pre-filled

    batch = ManualImportBatch.query.first()
    assert batch is not None
    assert len(batch.items) == 2
    assert batch.items[0]["status"] == "fetched"
    assert batch.current_index == 0


def test_bulk_fetch_partial_failure_shows_summary_and_fallback_in_sequence(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({
            "https://good.test/1": "Good Job",
            "https://bad.test/2": FetchFailed("That site declined the request."),
        }),
    )

    resp = client.post(
        "/jobs/import/fetch",
        data={"urls": "https://good.test/1\nhttps://bad.test/2"},
        follow_redirects=True,
    )
    assert b"Fetched 1 of 2" in resp.data
    assert b"1 failed" in resp.data

    batch = ManualImportBatch.query.first()
    assert batch.items[0]["status"] == "fetched"
    assert batch.items[1]["status"] == "failed"
    assert "declined the request" in batch.items[1]["error"]

    # first item (success) is shown pre-filled
    assert b"Good Job" in resp.data


def test_failed_url_surfaces_fallback_message_and_empty_title_on_its_turn(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({
            "https://good.test/1": "Good Job",
            "https://bad.test/2": FetchFailed("Could not reach that page (ConnectionError)."),
        }),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://good.test/1\nhttps://bad.test/2"})

    # save item 1, advancing to item 2 (the failed one)
    resp = client.post(
        "/jobs/import/save",
        data={
            "batch_index": "0",
            "title": "Good Job",
            "company_name": "Good Co",
            "application_url": "https://good.test/1",
        },
        follow_redirects=True,
    )
    assert b"Reviewing 2 of 2" in resp.data
    assert b"Could not reach that page" in resp.data
    assert b"Paste the text yourself" in resp.data
    # title field is empty for the failed item - nothing to prefill
    assert b'value="Good Job"' not in resp.data.split(b"Job title")[-1][:500]


# --- de-dup, cap enforcement ----------------------------------------------

def test_batch_deduplicates_urls_preserving_order(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://a.test/1\nhttps://a.test/1"})
    batch = ManualImportBatch.query.first()
    assert len(batch.items) == 1


def test_batch_caps_at_max_urls_and_flags_truncation(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    urls = [f"https://site{i}.test/job" for i in range(15)]
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({u: f"Job {i}" for i, u in enumerate(urls)}),
    )

    resp = client.post("/jobs/import/fetch", data={"urls": "\n".join(urls)}, follow_redirects=True)
    batch = ManualImportBatch.query.first()
    assert len(batch.items) == 10  # MAX_BATCH_URLS
    assert b"Only the first 10 URLs" in resp.data


# --- save/skip/advance/complete -------------------------------------------

def test_saving_an_item_advances_batch_and_creates_job(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://b.test/2": "Job B"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://b.test/2"})

    resp = client.post(
        "/jobs/import/save",
        data={"batch_index": "0", "title": "Job A", "company_name": "Company A", "application_url": "https://a.test/1"},
        follow_redirects=True,
    )
    assert b"Reviewing 2 of 2" in resp.data
    assert Job.query.filter_by(title="Job A").first() is not None

    batch = ManualImportBatch.query.first()
    assert batch.current_index == 1
    assert batch.items[0]["status"] == "saved"


def test_skipping_an_item_advances_without_creating_a_job(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://b.test/2": "Job B"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://b.test/2"})

    resp = client.post("/jobs/import/skip", follow_redirects=True)
    assert b"Reviewing 2 of 2" in resp.data
    assert Job.query.count() == 0

    batch = ManualImportBatch.query.first()
    assert batch.items[0]["status"] == "skipped"
    assert batch.current_index == 1


def test_completing_a_batch_deletes_it_and_shows_summary(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"})

    resp = client.post(
        "/jobs/import/save",
        data={"batch_index": "0", "title": "Job A", "company_name": "Company A", "application_url": "https://a.test/1"},
        follow_redirects=True,
    )
    assert b"Batch complete: 1 imported" in resp.data
    assert ManualImportBatch.query.count() == 0


def test_cancel_deletes_the_batch(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://b.test/2": "Job B"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://b.test/2"})
    assert ManualImportBatch.query.count() == 1

    resp = client.post("/jobs/import/cancel", follow_redirects=True)
    assert ManualImportBatch.query.count() == 0
    assert b"Import batch cancelled" in resp.data
    # back to the blank fetch form, not a review step
    assert b"1. Fetch from a URL" in resp.data


def test_new_fetch_replaces_an_in_progress_batch(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://c.test/3": "Job C"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"})
    assert ManualImportBatch.query.first().items[0]["url"] == "https://a.test/1"

    client.post("/jobs/import/fetch", data={"urls": "https://c.test/3"})
    assert ManualImportBatch.query.count() == 1  # old batch replaced, not accumulated
    new_batch = ManualImportBatch.query.first()
    assert new_batch.items[0]["url"] == "https://c.test/3"
    assert len(new_batch.items) == 1  # doesn't still contain the old item


def test_get_import_resumes_an_in_progress_batch(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://b.test/2": "Job B"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://b.test/2"})

    resp = client.get("/jobs/import")
    assert b"Reviewing 1 of 2" in resp.data
    assert b"Job A" in resp.data


# --- the cross-batch isolation fix ----------------------------------------

def test_standalone_save_without_batch_index_does_not_consume_an_in_progress_batch(client, db, make_user, monkeypatch):
    """A save that doesn't declare which batch item it belongs to (e.g. the
    bookmarklet path, which never uses a batch) must not silently advance
    some unrelated in-progress batch just because one happens to exist."""
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://b.test/2": "Job B"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://b.test/2"})
    batch = ManualImportBatch.query.first()
    assert batch.current_index == 0

    # a standalone save with no batch_index, as the bookmarklet page sends
    resp = client.post(
        "/jobs/import/save",
        data={"title": "Standalone Job", "company_name": "Standalone Co", "application_url": "https://standalone.test"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Job.query.filter_by(title="Standalone Job").first() is not None

    # the in-progress batch must be completely untouched
    batch = ManualImportBatch.query.first()
    assert batch is not None
    assert batch.current_index == 0
    assert batch.items[0]["status"] == "fetched"


def test_save_with_stale_batch_index_does_not_advance_current_batch(client, db, make_user, monkeypatch):
    make_logged_in_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A", "https://b.test/2": "Job B"}),
    )
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://b.test/2"})

    # a save claiming to be for item index 1, while the batch is still on item 0
    resp = client.post(
        "/jobs/import/save",
        data={"batch_index": "1", "title": "Mismatched Job", "company_name": "Co", "application_url": "https://x.test"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    batch = ManualImportBatch.query.first()
    assert batch.current_index == 0  # unchanged


# --- per-user isolation ----------------------------------------------------

def test_batches_are_isolated_per_user(client, db, make_user, monkeypatch):
    make_user(email="userone@example.com", password="Password123!")
    make_user(email="usertwo@example.com", password="Password123!")
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        fake_fetch_factory({"https://a.test/1": "Job A"}),
    )

    login(client, "userone@example.com", "Password123!")
    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"})
    assert ManualImportBatch.query.count() == 1

    client.get("/auth/logout")
    login(client, "usertwo@example.com", "Password123!")
    resp = client.get("/jobs/import")
    # user two should see a blank form, not user one's in-progress batch
    assert b"Reviewing" not in resp.data
    assert ManualImportBatch.query.count() == 1  # still just user one's
