"""Unit tests for app/ai/manual_import_extraction.py (manual import
extraction pass, 2026-08-30) - grounding, fallback behavior, and the
line-exclusion description-cleaning mechanism. Route-level lazy-trigger
and caching behavior lives in tests/test_manual_import_extraction_flow.py.
"""
from app.ai.manual_import_extraction import (
    _clean_description,
    _validate_and_ground,
    extract_manual_import_fields,
)
from app.ai.provider import AIProvider, AIProviderError, AIResponse
from app.models.ai import AIUsage

PAGE_TITLE = "Ausbildung Mechatroniker (m/w/d) | Karriere bei Beispiel GmbH"
RAW_TEXT = (
    "Zur Startseite\n"
    "Karriere\n"
    "Ausbildung Mechatroniker (m/w/d)\n"
    "Beispiel GmbH sucht dich fuer Leipzig.\n"
    "Startdatum: 01.09.2027\n"
    "Das bringst du mit:\n"
    "- Guter Schulabschluss\n"
    "Jetzt bewerben\n"
    "Impressum\n"
    "Datenschutz\n"
)


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text=None, raise_error=None):
        self._text = text
        self._raise_error = raise_error
        self.last_prompt = None

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        self.last_prompt = user_prompt
        if self._raise_error:
            raise self._raise_error
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=5, output_tokens=5)


# --- _validate_and_ground() ---

def test_validate_and_ground_grounded_values_pass_through():
    raw = (
        '{"title": "Ausbildung Mechatroniker (m/w/d)", "company_name": "Beispiel GmbH", '
        '"location": "Leipzig", "start_date": "01.09.2027", "exclude_line_numbers": []}'
    )
    result = _validate_and_ground(raw, PAGE_TITLE, RAW_TEXT)
    assert result["title"] == "Ausbildung Mechatroniker (m/w/d)"
    assert result["company_name"] == "Beispiel GmbH"
    assert result["location"] == "Leipzig"
    assert result["start_date"] == "01.09.2027"


def test_validate_and_ground_ungrounded_company_is_dropped():
    # "Fabricated GmbH" never appears anywhere in the source text - must
    # be dropped, not trusted, even though it's a plausible-looking name.
    raw = (
        '{"title": null, "company_name": "Fabricated GmbH", "location": null, '
        '"start_date": null, "exclude_line_numbers": []}'
    )
    result = _validate_and_ground(raw, PAGE_TITLE, RAW_TEXT)
    assert result["company_name"] is None


def test_validate_and_ground_ungrounded_start_date_is_dropped():
    raw = '{"title": null, "company_name": null, "location": null, "start_date": "15.03.2028", "exclude_line_numbers": []}'
    result = _validate_and_ground(raw, PAGE_TITLE, RAW_TEXT)
    assert result["start_date"] is None


def test_validate_and_ground_title_can_be_grounded_via_body_not_just_title_tag():
    # The clean title genuinely appears in the body even though it's not
    # an exact substring of the raw <title> tag (which has extra branding).
    raw = '{"title": "Ausbildung Mechatroniker (m/w/d)", "company_name": null, "location": null, "start_date": null, "exclude_line_numbers": []}'
    result = _validate_and_ground(raw, PAGE_TITLE, RAW_TEXT)
    assert result["title"] == "Ausbildung Mechatroniker (m/w/d)"


def test_validate_and_ground_malformed_json_returns_none():
    assert _validate_and_ground("not json at all", PAGE_TITLE, RAW_TEXT) is None


def test_validate_and_ground_markdown_fenced_json_is_parsed():
    # Gemini (and other models) routinely wrap a JSON reply in a markdown
    # code fence even when told to respond with JSON only - live-verified
    # against the real provider - must still parse correctly.
    raw = (
        "```json\n"
        '{"title": null, "company_name": "Beispiel GmbH", "location": null, '
        '"start_date": null, "exclude_line_numbers": []}\n'
        "```"
    )
    result = _validate_and_ground(raw, PAGE_TITLE, RAW_TEXT)
    assert result is not None
    assert result["company_name"] == "Beispiel GmbH"


def test_validate_and_ground_wrong_shape_returns_none():
    assert _validate_and_ground('{"title": null}', PAGE_TITLE, RAW_TEXT) is None


def test_validate_and_ground_non_int_exclude_line_numbers_returns_none():
    raw = '{"title": null, "company_name": null, "location": null, "start_date": null, "exclude_line_numbers": ["a", "b"]}'
    assert _validate_and_ground(raw, PAGE_TITLE, RAW_TEXT) is None


# --- _clean_description() ---

# RAW_TEXT, 1-based: 1 Zur Startseite / 2 Karriere / 3 Ausbildung Mechatroniker (m/w/d) /
# 4 Beispiel GmbH sucht dich fuer Leipzig. / 5 Startdatum: 01.09.2027 /
# 6 Das bringst du mit: / 7 - Guter Schulabschluss / 8 Jetzt bewerben / 9 Impressum / 10 Datenschutz

def test_clean_description_removes_matching_line_numbers():
    cleaned = _clean_description(RAW_TEXT, [1, 2, 8, 9, 10])
    assert "Zur Startseite" not in cleaned
    assert "Impressum" not in cleaned
    assert "Ausbildung Mechatroniker (m/w/d)" in cleaned
    assert "Startdatum: 01.09.2027" in cleaned


def test_clean_description_out_of_range_number_is_a_no_op():
    # A number outside the real line range just doesn't match anything -
    # never removes real content, never errors.
    cleaned = _clean_description(RAW_TEXT, [999])
    assert cleaned == RAW_TEXT


def test_clean_description_empty_exclude_list_returns_original():
    assert _clean_description(RAW_TEXT, []) == RAW_TEXT


def test_clean_description_never_adds_content_only_removes():
    # Exhaustive check: every line of the cleaned output must already
    # exist, verbatim, in the original - the description can only shrink.
    cleaned = _clean_description(RAW_TEXT, [1, 9])
    original_lines = set(RAW_TEXT.splitlines())
    for line in cleaned.splitlines():
        assert line in original_lines


def test_clean_description_over_aggressive_exclusion_falls_back_to_raw_text():
    # Excluding nearly everything must be treated as a malfunction, not
    # trusted cleaning - falls back to the untouched, still-safe raw text.
    # A cookie-consent-heavy real page can legitimately be ~80% chrome (see
    # MAX_EXCLUDED_FRACTION's docstring), so this needs a text where the
    # excluded fraction clears the current, deliberately high cap.
    long_text = "\n".join(f"Chrome line {i}" for i in range(1, 201)) + "\nKeep me."
    almost_everything = list(range(1, 201))  # every chrome line, real content untouched
    cleaned = _clean_description(long_text, almost_everything)
    assert cleaned == long_text


# --- extract_manual_import_fields() - fallback paths ---

def test_mock_mode_returns_exact_baseline_fallback(app):
    with app.test_request_context("/"):
        result = extract_manual_import_fields(PAGE_TITLE, RAW_TEXT, user_id=1)
    assert result == {
        "title": PAGE_TITLE,
        "company_name": None,
        "location": None,
        "start_date": None,
        "description": RAW_TEXT,
    }


def test_provider_error_returns_exact_baseline_fallback(app, db, make_user, monkeypatch):
    # log_event() now fires for this path (admin-visible failure logging,
    # see app/ai/manual_import_extraction.py) - needs a real user row for
    # the SystemLog FK, same reasoning as the malformed-response test below.
    user = make_user(email="extract-providererror@example.com")
    fake = FakeProvider(raise_error=AIProviderError("provider down"))
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)
    with app.test_request_context("/"):
        result = extract_manual_import_fields(PAGE_TITLE, RAW_TEXT, user_id=user.id)
    assert result == {
        "title": PAGE_TITLE,
        "company_name": None,
        "location": None,
        "start_date": None,
        "description": RAW_TEXT,
    }


def test_malformed_response_returns_exact_baseline_fallback(app, db, make_user, monkeypatch):
    # A malformed response still reached a real provider (record_usage()
    # fires regardless - same as job_requirements_extraction.py), so this
    # needs a real user row for that FK, unlike the mock/error paths above
    # which never reach record_usage() at all.
    user = make_user(email="extract-malformed@example.com")
    fake = FakeProvider(text="not json")
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)
    with app.test_request_context("/"):
        result = extract_manual_import_fields(PAGE_TITLE, RAW_TEXT, user_id=user.id)
    assert result == {
        "title": PAGE_TITLE,
        "company_name": None,
        "location": None,
        "start_date": None,
        "description": RAW_TEXT,
    }


def test_successful_extraction_populates_grounded_fields(app, db, make_user, monkeypatch):
    user = make_user(email="extract1@example.com")
    fake_json = (
        '{"title": "Ausbildung Mechatroniker (m/w/d)", "company_name": "Beispiel GmbH", '
        '"location": "Leipzig", "start_date": "01.09.2027", '
        '"exclude_line_numbers": [1, 2, 8, 9, 10]}'
    )
    fake = FakeProvider(text=fake_json)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    with app.test_request_context("/"):
        result = extract_manual_import_fields(PAGE_TITLE, RAW_TEXT, user_id=user.id)

    assert result["title"] == "Ausbildung Mechatroniker (m/w/d)"
    assert result["company_name"] == "Beispiel GmbH"
    assert result["location"] == "Leipzig"
    assert result["start_date"] == "01.09.2027"
    assert "Zur Startseite" not in result["description"]
    assert "Startdatum: 01.09.2027" in result["description"]


def test_successful_real_call_is_logged_via_record_usage(app, db, make_user, monkeypatch):
    user = make_user(email="extract2@example.com")
    fake_json = '{"title": null, "company_name": null, "location": null, "start_date": null, "exclude_line_numbers": []}'
    fake = FakeProvider(text=fake_json)
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: fake)

    assert AIUsage.query.count() == 0
    with app.test_request_context("/"):
        extract_manual_import_fields(PAGE_TITLE, RAW_TEXT, user_id=user.id)

    entry = AIUsage.query.first()
    assert entry is not None
    assert entry.feature == "manual_import_extraction"
    assert entry.user_id == user.id


def test_mock_mode_does_not_log_usage(app, db, make_user):
    user = make_user(email="extract3@example.com")
    with app.test_request_context("/"):
        extract_manual_import_fields(PAGE_TITLE, RAW_TEXT, user_id=user.id)
    assert AIUsage.query.count() == 0
