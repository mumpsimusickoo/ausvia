"""Route-level tests for the manual import extraction pass (2026-08-30):
lazy triggering (only the batch item actually being reviewed), caching
on the item (never re-run for an already-reviewed item), and graceful
fallback under AI unavailability - app/jobs/routes.py's
_ensure_item_extracted(), app/ai/manual_import_extraction.py.
"""
import app.jobs.routes as routes_module
from app.ai.provider import AIProvider, AIProviderError, AIResponse
from app.models import ManualImportBatch
from app.models.ai import AIUsage
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text=None, raise_error=None):
        self._text = text
        self._raise_error = raise_error

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        if self._raise_error:
            raise self._raise_error
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=5, output_tokens=5)


def _fake_fetch(results):
    from app.jobs.manual_import import FetchFailed

    def _fetch(url):
        outcome = results.get(url)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return _fetch


GROUNDED_JSON = (
    '{"title": "Ausbildung Mechatroniker (m/w/d)", "company_name": "Beispiel GmbH", '
    '"location": "Leipzig", "start_date": "01.09.2027", "exclude_line_numbers": [1, 5]}'
)

ITEM_TEXT = (
    "Zur Startseite\n"
    "Ausbildung Mechatroniker (m/w/d)\n"
    "Beispiel GmbH sucht dich fuer Leipzig.\n"
    "Startdatum: 01.09.2027\n"
    "Impressum\n"
)


def _make_admin_or_user(db, client, make_user, email="extractflow@example.com"):
    make_user(email=email, password="Password123!")
    login(client, email, "Password123!")


def test_extraction_runs_lazily_only_for_currently_reviewed_item(client, db, make_user, monkeypatch):
    """Fetching a 3-item batch must not extract anything until the item
    is actually the one being displayed for review - and only ever the
    current one, never the others sitting pending behind it."""
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({
            "https://a.test/1": {"page_title": "Title A", "text": ITEM_TEXT},
            "https://b.test/2": {"page_title": "Title B", "text": ITEM_TEXT},
            "https://c.test/3": {"page_title": "Title C", "text": ITEM_TEXT},
        }),
    )

    calls = []

    def fake_extract(page_title, text, user_id):
        calls.append(page_title)
        return {"title": page_title, "company_name": None, "location": None, "start_date": None, "description": text}

    monkeypatch.setattr(routes_module, "extract_manual_import_fields", fake_extract)

    client.post(
        "/jobs/import/fetch",
        data={"urls": "https://a.test/1\nhttps://b.test/2\nhttps://c.test/3"},
        follow_redirects=True,
    )

    # Only item A (the one now being reviewed) was ever extracted.
    assert calls == ["Title A"]

    batch = ManualImportBatch.query.first()
    assert batch.items[0].get("extracted") is True
    assert batch.items[1].get("extracted") is not True
    assert batch.items[2].get("extracted") is not True


def test_extraction_result_is_cached_on_the_item_not_rerun(client, db, make_user, monkeypatch):
    """Revisiting the same item (e.g. GET /jobs/import resuming an
    in-progress batch) must not burn a second AI call for the same URL."""
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Title A", "text": ITEM_TEXT}}),
    )

    calls = []

    def fake_extract(page_title, text, user_id):
        calls.append(page_title)
        return {"title": page_title, "company_name": None, "location": None, "start_date": None, "description": text}

    monkeypatch.setattr(routes_module, "extract_manual_import_fields", fake_extract)

    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"})
    assert len(calls) == 1

    # Revisit the same still-in-progress item several times.
    client.get("/jobs/import")
    client.get("/jobs/import")
    client.get("/jobs/import")
    assert len(calls) == 1  # still just the one real call


def test_extraction_advances_to_next_item_only_when_that_item_is_shown(client, db, make_user, monkeypatch):
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({
            "https://a.test/1": {"page_title": "Title A", "text": ITEM_TEXT},
            "https://b.test/2": {"page_title": "Title B", "text": ITEM_TEXT},
        }),
    )

    calls = []

    def fake_extract(page_title, text, user_id):
        calls.append(page_title)
        return {"title": page_title, "company_name": None, "location": None, "start_date": None, "description": text}

    monkeypatch.setattr(routes_module, "extract_manual_import_fields", fake_extract)

    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1\nhttps://b.test/2"})
    assert calls == ["Title A"]

    client.post(
        "/jobs/import/save",
        data={"batch_index": "0", "title": "Title A", "company_name": "Co", "application_url": "https://a.test/1"},
        follow_redirects=True,
    )
    # Now item B is the current one being reviewed - extracted exactly once.
    assert calls == ["Title A", "Title B"]


def test_review_form_populated_with_grounded_extraction_result(client, db, make_user, monkeypatch):
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": ITEM_TEXT}}),
    )
    fake = FakeProvider(text=GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    assert "Ausbildung Mechatroniker (m/w/d)" in body
    assert "Beispiel GmbH" in body
    assert "Leipzig" in body
    assert "01.09.2027" in body


def test_review_form_falls_back_to_raw_baseline_when_ai_unconfigured(client, db, make_user, monkeypatch):
    # Default test config: AI_PROVIDER is mock - confirms the review form
    # shows exactly today's pre-extraction baseline (raw title, raw text,
    # company/location/start date blank), not broken or empty.
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Page Title", "text": ITEM_TEXT}}),
    )

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    assert "Raw Page Title" in body
    assert "Zur Startseite" in body  # untouched raw text, chrome included


def test_review_form_falls_back_when_provider_errors(client, db, make_user, monkeypatch):
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Page Title", "text": ITEM_TEXT}}),
    )
    fake = FakeProvider(raise_error=AIProviderError("provider unavailable"))
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Raw Page Title" in body


def test_failed_fetch_item_never_triggers_extraction(client, db, make_user, monkeypatch):
    from app.jobs.manual_import import FetchFailed

    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://bad.test/1": FetchFailed("blocked")}),
    )

    calls = []
    monkeypatch.setattr(
        routes_module, "extract_manual_import_fields",
        lambda page_title, text, user_id: calls.append(1) or {},
    )

    client.post("/jobs/import/fetch", data={"urls": "https://bad.test/1"}, follow_redirects=True)
    assert calls == []


