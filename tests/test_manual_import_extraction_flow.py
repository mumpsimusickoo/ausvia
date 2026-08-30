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
from app.models.job import Job
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
    '"location": "Leipzig", "start_date": "01.09.2027", "salary": null, "contact_person": null, "contact_email": null, "exclude_line_numbers": [1, 5]}'
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
        return {"title": page_title, "company_name": None, "location": None, "start_date": None, "salary": None,
        "contact_person": None,
        "contact_email": None, "description": text}

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
        return {"title": page_title, "company_name": None, "location": None, "start_date": None, "salary": None,
        "contact_person": None,
        "contact_email": None, "description": text}

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
        return {"title": page_title, "company_name": None, "location": None, "start_date": None, "salary": None,
        "contact_person": None,
        "contact_email": None, "description": text}

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


# --- Salary follow-up pass (2026-08-30) ---

SALARY_TEXT = (
    "Zur Startseite\n"
    "Ausbildung Mechatroniker (m/w/d)\n"
    "Beispiel GmbH sucht dich fuer Leipzig.\n"
    "Startdatum: 01.09.2027\n"
    "Verguetung: 1.272 Euro im ersten Ausbildungsjahr\n"
    "Impressum\n"
)

SALARY_GROUNDED_JSON = (
    '{"title": "Ausbildung Mechatroniker (m/w/d)", "company_name": "Beispiel GmbH", '
    '"location": "Leipzig", "start_date": "01.09.2027", '
    '"salary": "1.272 Euro im ersten Ausbildungsjahr", "contact_person": null, "contact_email": null, "exclude_line_numbers": [1, 6]}'
)


def test_review_form_populated_with_grounded_salary(client, db, make_user, monkeypatch):
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": SALARY_TEXT}}),
    )
    fake = FakeProvider(text=SALARY_GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    assert 'value="1.272 Euro im ersten Ausbildungsjahr"' in body


def test_review_form_leaves_salary_blank_when_genuinely_absent(client, db, make_user, monkeypatch):
    # GROUNDED_JSON's salary is null - ITEM_TEXT never states a figure at
    # all, so a correct extraction must leave the field blank rather than
    # guess or estimate one, same discipline as start date.
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": ITEM_TEXT}}),
    )
    fake = FakeProvider(text=GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    idx = body.find('id="salary"')
    assert idx != -1
    field_html = body[idx:idx + 200]
    assert 'value=""' in field_html


def test_ungrounded_salary_is_dropped_not_saved(client, db, make_user, monkeypatch):
    # A plausible-looking figure the AI names but that never actually
    # appears in the source - must be dropped, never trusted as a guess.
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": ITEM_TEXT}}),
    )
    fabricated_json = (
        '{"title": null, "company_name": null, "location": null, "start_date": null, '
        '"salary": "9.999 Euro pro Monat", "contact_person": null, "contact_email": null, "exclude_line_numbers": []}'
    )
    fake = FakeProvider(text=fabricated_json)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    assert "9.999" not in body


# --- contact_person/contact_email (contact-info follow-up pass, 2026-08-30) ---

CONTACT_TEXT = (
    "Zur Startseite\n"
    "Ausbildung Mechatroniker (m/w/d)\n"
    "Beispiel GmbH sucht dich fuer Leipzig.\n"
    "Startdatum: 01.09.2027\n"
    "Ansprechpartnerin: Frau Julia Weber, julia.weber@beispiel.de\n"
    "Impressum\n"
)

CONTACT_GROUNDED_JSON = (
    '{"title": "Ausbildung Mechatroniker (m/w/d)", "company_name": "Beispiel GmbH", '
    '"location": "Leipzig", "start_date": "01.09.2027", "salary": null, '
    '"contact_person": "Frau Julia Weber", "contact_email": "julia.weber@beispiel.de", '
    '"exclude_line_numbers": [1, 6]}'
)


def test_review_form_populated_with_grounded_contact_info(client, db, make_user, monkeypatch):
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": CONTACT_TEXT}}),
    )
    fake = FakeProvider(text=CONTACT_GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    assert 'value="Frau Julia Weber"' in body
    assert 'value="julia.weber@beispiel.de"' in body


def test_review_form_leaves_contact_info_blank_when_genuinely_absent(client, db, make_user, monkeypatch):
    # GROUNDED_JSON's contact_person/contact_email are null - ITEM_TEXT
    # never states either, so a correct extraction leaves both blank
    # rather than guess, same discipline as salary/start date.
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": ITEM_TEXT}}),
    )
    fake = FakeProvider(text=GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    for field_id in ("id=\"contact_person\"", "id=\"contact_email\""):
        idx = body.find(field_id)
        assert idx != -1
        assert 'value=""' in body[idx:idx + 200]


def test_ungrounded_contact_info_is_dropped_not_saved(client, db, make_user, monkeypatch):
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": ITEM_TEXT}}),
    )
    fabricated_json = (
        '{"title": null, "company_name": null, "location": null, "start_date": null, "salary": null, '
        '"contact_person": "Frau Erfundene Person", "contact_email": "fake@nowhere.example", '
        '"exclude_line_numbers": []}'
    )
    fake = FakeProvider(text=fabricated_json)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    body = resp.data.decode("utf-8")
    assert "Erfundene" not in body
    assert "fake@nowhere.example" not in body


def test_saving_grounded_contact_info_populates_job_row(client, db, make_user, monkeypatch):
    # End-to-end: extraction -> review form -> Save -> the real Job row,
    # confirming the secondary consequence (Application.contact_email
    # seeding, see tests/test_applications.py) has real data to draw from.
    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr(
        "app.jobs.routes.fetch_and_extract_text",
        _fake_fetch({"https://a.test/1": {"page_title": "Raw Title | Site", "text": CONTACT_TEXT}}),
    )
    fake = FakeProvider(text=CONTACT_GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    client.post("/jobs/import/fetch", data={"urls": "https://a.test/1"}, follow_redirects=True)
    client.post(
        "/jobs/import/save",
        data={
            "batch_index": "0",
            "title": "Ausbildung Mechatroniker (m/w/d)",
            "company_name": "Beispiel GmbH",
            "location": "Leipzig",
            "start_date": "01.09.2027",
            "contact_person": "Frau Julia Weber",
            "contact_email": "julia.weber@beispiel.de",
            "description": CONTACT_TEXT,
        },
        follow_redirects=True,
    )

    job = Job.query.filter_by(title="Ausbildung Mechatroniker (m/w/d)").first()
    assert job is not None
    assert job.contact_person == "Frau Julia Weber"
    assert job.contact_email == "julia.weber@beispiel.de"


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


# --- Pasted-text follow-up (2026-08-30): the same extraction pipeline,
# triggered by a Save click on a failed-fetch item with pasted text,
# instead of by a successful fetch. See app/jobs/routes.py's
# _ensure_pasted_text_extracted() and the import_save() interception
# right before review_form.validate_on_submit(). ---

def _start_failed_batch(client, db, make_user, monkeypatch, url="https://bad.test/1"):
    from app.jobs.manual_import import FetchFailed

    _make_admin_or_user(db, client, make_user)
    monkeypatch.setattr("app.jobs.routes.fetch_and_extract_text", _fake_fetch({url: FetchFailed("blocked")}))
    client.post("/jobs/import/fetch", data={"urls": url}, follow_redirects=True)


def test_pasted_text_extraction_runs_on_save_and_populates_review_form(client, db, make_user, monkeypatch):
    _start_failed_batch(client, db, make_user, monkeypatch)
    fake = FakeProvider(text=GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post(
        "/jobs/import/save",
        data={"batch_index": "0", "description": ITEM_TEXT, "application_url": "https://bad.test/1"},
        follow_redirects=True,
    )
    body = resp.data.decode("utf-8")
    assert "Ausbildung Mechatroniker (m/w/d)" in body
    assert "Beispiel GmbH" in body
    assert "Leipzig" in body
    assert "01.09.2027" in body
    # First save on a failed item is "populate and let the user confirm" -
    # the job must not exist yet, same discipline as the fetch path never
    # silently committing an AI value the user hasn't seen.
    assert Job.query.count() == 0

    batch = ManualImportBatch.query.first()
    assert batch.items[0]["status"] == "failed"  # unchanged - not yet saved
    assert batch.items[0]["extracted"] is True


def test_pasted_text_extraction_does_not_overwrite_values_the_user_typed(client, db, make_user, monkeypatch):
    _start_failed_batch(client, db, make_user, monkeypatch)
    fake = FakeProvider(text=GROUNDED_JSON)  # would suggest "Beispiel GmbH"
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    resp = client.post(
        "/jobs/import/save",
        data={
            "batch_index": "0", "description": ITEM_TEXT,
            "company_name": "Company I Typed Myself GmbH",
            "application_url": "https://bad.test/1",
        },
        follow_redirects=True,
    )
    body = resp.data.decode("utf-8")
    # The company FIELD's value specifically - not a whole-body substring
    # check, since "Beispiel GmbH" is also part of ITEM_TEXT's genuine
    # posting content and legitimately survives into the cleaned
    # description regardless of which company name wins.
    assert 'value="Company I Typed Myself GmbH"' in body
    assert 'value="Beispiel GmbH"' not in body  # the AI suggestion never overrides real human input
    # Fields the user left blank are still filled in from extraction.
    assert 'value="Leipzig"' in body


def test_pasted_text_extraction_second_save_actually_creates_the_job(client, db, make_user, monkeypatch):
    _start_failed_batch(client, db, make_user, monkeypatch)
    calls = []

    def fake_extract(page_title, text, user_id):
        calls.append(1)
        return {
            "title": "Ausbildung Mechatroniker (m/w/d)", "company_name": "Beispiel GmbH",
            "location": "Leipzig", "start_date": "01.09.2027", "salary": None,
        "contact_person": None,
        "contact_email": None, "description": text,
        }

    monkeypatch.setattr(routes_module, "extract_manual_import_fields", fake_extract)

    # First save: populates and re-shows the review form, doesn't save.
    client.post(
        "/jobs/import/save",
        data={"batch_index": "0", "description": ITEM_TEXT, "application_url": "https://bad.test/1"},
        follow_redirects=True,
    )
    assert len(calls) == 1
    assert Job.query.count() == 0

    # Second save (the user confirming the now-populated form): actually
    # creates the job, and does NOT burn a second AI call for this item.
    resp = client.post(
        "/jobs/import/save",
        data={
            "batch_index": "0", "title": "Ausbildung Mechatroniker (m/w/d)",
            "company_name": "Beispiel GmbH", "location": "Leipzig", "start_date": "01.09.2027",
            "description": ITEM_TEXT, "application_url": "https://bad.test/1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert len(calls) == 1  # still just the one real call
    assert Job.query.count() == 1
    job = Job.query.first()
    assert job.title == "Ausbildung Mechatroniker (m/w/d)"
    assert job.company_name == "Beispiel GmbH"


def test_pasted_text_extraction_falls_back_gracefully_when_ai_unconfigured(client, db, make_user, monkeypatch):
    # Default test config: AI_PROVIDER is mock - confirms saving pasted
    # text still works exactly as it did before this feature existed:
    # the user's own typed title/company go straight through, no crash,
    # no AI-suggested content anywhere.
    _start_failed_batch(client, db, make_user, monkeypatch)

    resp = client.post(
        "/jobs/import/save",
        data={
            "batch_index": "0", "title": "Ausbildung Mechatroniker (m/w/d)",
            "company_name": "Beispiel GmbH", "description": ITEM_TEXT,
            "application_url": "https://bad.test/1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Job.query.count() == 1  # title+company already present -> saves immediately, no review loop


def test_pasted_text_extraction_skipped_when_description_is_blank(client, db, make_user, monkeypatch):
    _start_failed_batch(client, db, make_user, monkeypatch)
    calls = []
    monkeypatch.setattr(
        routes_module, "extract_manual_import_fields",
        lambda page_title, text, user_id: calls.append(1) or {},
    )

    resp = client.post(
        "/jobs/import/save",
        data={"batch_index": "0", "application_url": "https://bad.test/1"},
        follow_redirects=True,
    )
    assert calls == []
    assert resp.status_code == 200
    assert b"job title and company" in resp.data  # normal validation error, unchanged behavior


def test_pasted_text_extraction_is_rate_limited(client, db, make_user, monkeypatch):
    """Shares app/ai/manual_import_extraction.py's single 30/hour bucket
    with the fetch-success path - both call the exact same
    extract_manual_import_fields(), so the existing rate limit already
    covers this trigger point too. Verified via the real (mock) provider
    decline path staying silent under a simulated-exceeded limit, mirror-
    ing the fetch-path rate-limit test's own approach."""
    from flask_limiter.errors import RateLimitExceeded

    _start_failed_batch(client, db, make_user, monkeypatch)
    fake = FakeProvider(text=GROUNDED_JSON)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    def raise_rate_limited():
        from types import SimpleNamespace

        raise RateLimitExceeded(SimpleNamespace(error_message=None, limit="30 per 1 hour"))

    monkeypatch.setattr("app.ai.manual_import_extraction._consume_extraction_rate_limit", raise_rate_limited)

    resp = client.post(
        "/jobs/import/save",
        data={"batch_index": "0", "description": ITEM_TEXT, "application_url": "https://bad.test/1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    # Degrades to the raw-pasted-text baseline, same as the fetch path -
    # never a 429, never blocks the save. The company FIELD's value
    # specifically - "Beispiel GmbH" legitimately still appears as part
    # of ITEM_TEXT's untouched raw content either way.
    assert "Zur Startseite" in body
    assert 'value="Beispiel GmbH"' not in body


