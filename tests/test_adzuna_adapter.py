"""Tests for app/jobs/adapters/adzuna.py, mocking requests.get directly -
same fake-response pattern as tests/test_gemini_provider.py's FakeClient,
just one layer lower here (this IS the HTTP client, not a caller of an
SDK). No real network calls, no real credentials.
"""
import requests

import pytest

from app.jobs.adapters.adzuna import AdzunaAdapter, AdzunaAdapterError


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, malformed=False):
        self.status_code = status_code
        self._json_data = json_data
        self._malformed = malformed

    def json(self):
        if self._malformed:
            raise ValueError("not valid json")
        return self._json_data


def make_adapter():
    return AdzunaAdapter(app_id="fake-id", app_key="fake-key", country="de")


SAMPLE_RESULT = {
    "id": 12345,
    "title": "Ausbildung Elektroniker (m/w/d)",
    "company": {"display_name": "TestFirma GmbH"},
    "location": {"display_name": "Stuttgart"},
    "description": "Wir bilden aus...",
    "salary_min": 800.0,
    "salary_max": 1000.0,
    "contract_type": "full_time",
    "redirect_url": "https://www.adzuna.de/land/ad/12345",
}


def test_successful_search_returns_results(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return FakeResponse(200, {"results": [SAMPLE_RESULT]})

    monkeypatch.setattr(requests, "get", fake_get)
    adapter = make_adapter()
    results = adapter.search("Elektroniker", location="Stuttgart", results_size=25)

    assert results == [SAMPLE_RESULT]
    url, params = calls[0]
    assert url == "https://api.adzuna.com/v1/api/jobs/de/search/1"
    assert params["app_id"] == "fake-id"
    assert params["app_key"] == "fake-key"
    assert params["what"] == "Elektroniker"
    assert params["where"] == "Stuttgart"


def test_empty_results_returns_empty_list(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse(200, {"results": []}))
    assert make_adapter().search("Elektroniker") == []


def test_pagination_across_multiple_pages(monkeypatch):
    page1 = [dict(SAMPLE_RESULT, id=i) for i in range(25)]
    page2 = [dict(SAMPLE_RESULT, id=i) for i in range(25, 30)]
    responses = [FakeResponse(200, {"results": page1}), FakeResponse(200, {"results": page2})]

    def fake_get(url, params=None, timeout=None):
        return responses.pop(0)

    monkeypatch.setattr(requests, "get", fake_get)
    results = make_adapter().search("Elektroniker", results_size=30)
    assert len(results) == 30


def test_malformed_response_raises_adapter_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse(200, malformed=True))
    with pytest.raises(AdzunaAdapterError, match="malformed"):
        make_adapter().search("Elektroniker")


def test_unexpected_response_shape_raises_adapter_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse(200, {"unexpected": "shape"}))
    with pytest.raises(AdzunaAdapterError, match="unexpected response shape"):
        make_adapter().search("Elektroniker")


def test_401_raises_credentials_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse(401))
    with pytest.raises(AdzunaAdapterError, match="rejected the configured credentials"):
        make_adapter().search("Elektroniker")


def test_403_raises_credentials_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse(403))
    with pytest.raises(AdzunaAdapterError, match="rejected the configured credentials"):
        make_adapter().search("Elektroniker")


def test_429_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse(429))
    with pytest.raises(AdzunaAdapterError, match="rate limit"):
        make_adapter().search("Elektroniker")


def test_500_raises_generic_http_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse(500))
    with pytest.raises(AdzunaAdapterError, match="HTTP 500"):
        make_adapter().search("Elektroniker")


def test_timeout_raises_adapter_error(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(AdzunaAdapterError, match="timed out"):
        make_adapter().search("Elektroniker")


def test_connection_error_raises_adapter_error(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.ConnectionError("dns failed")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(AdzunaAdapterError, match="Could not reach Adzuna"):
        make_adapter().search("Elektroniker")


def test_credentials_never_leak_into_error_message(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.RequestException("failed for url with app_key=fake-key in it")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(AdzunaAdapterError) as exc_info:
        make_adapter().search("Elektroniker")
    assert "fake-key" not in str(exc_info.value)


def test_get_job_returns_none_no_detail_endpoint():
    assert make_adapter().get_job("12345") is None


def test_normalize_maps_all_documented_fields():
    normalized = make_adapter().normalize(SAMPLE_RESULT)
    assert normalized.source == "adzuna"
    assert normalized.external_id == "12345"
    assert normalized.title == "Ausbildung Elektroniker (m/w/d)"
    assert normalized.company_name == "TestFirma GmbH"
    assert normalized.location == "Stuttgart"
    assert normalized.salary == "800–1000"
    assert normalized.employment_type == "full_time"
    assert normalized.description == "Wir bilden aus..."
    assert normalized.application_url == "https://www.adzuna.de/land/ad/12345"
    assert normalized.source_url == "https://www.adzuna.de/land/ad/12345"
    assert normalized.raw == SAMPLE_RESULT


def test_normalize_does_not_fabricate_ausbildung_employment_type():
    # Regression check for the explicit "don't force fields" requirement -
    # Adzuna's contract_type is generic, not an apprenticeship confirmation,
    # so it must NOT fall back to NormalizedJob's "Ausbildung" default.
    raw = dict(SAMPLE_RESULT, contract_type=None)
    normalized = make_adapter().normalize(raw)
    assert normalized.employment_type is None


def test_normalize_handles_missing_optional_fields():
    minimal = {"id": 1, "title": "Some job"}
    normalized = make_adapter().normalize(minimal)
    assert normalized.title == "Some job"
    assert normalized.company_name is None
    assert normalized.location is None
    assert normalized.salary is None
    assert normalized.description is None


def test_normalize_missing_title_falls_back_to_untitled():
    normalized = make_adapter().normalize({"id": 1})
    assert normalized.title == "Untitled posting"


def test_normalize_single_salary_value_formatted_without_range():
    raw = dict(SAMPLE_RESULT, salary_min=900.0, salary_max=900.0)
    normalized = make_adapter().normalize(raw)
    assert normalized.salary == "900"
