"""Tests for app/jobs/adapters/jooble.py, mocking requests.post directly -
same fake-response pattern as tests/test_adzuna_adapter.py. No real
network calls, no real credentials.
"""
import requests

import pytest

from app.jobs.adapters.jooble import JoobleAdapter, JoobleAdapterError


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
    return JoobleAdapter(api_key="fake-jooble-key")


SAMPLE_JOB = {
    "id": 987654321,
    "title": "Ausbildung Mechatroniker",
    "location": "Hamburg",
    "snippet": "Wir suchen dich...",
    "salary": "1.000 EUR",
    "source": "jooble",
    "type": "Vollzeit",
    "link": "https://de.jooble.org/jdp/987654321",
    "company": "Beispiel AG",
    "updated": "2026-01-01T00:00:00.0000000",
}


def test_successful_search_returns_jobs(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append((url, json, headers))
        return FakeResponse(200, {"totalCount": 1, "jobs": [SAMPLE_JOB]})

    monkeypatch.setattr(requests, "post", fake_post)
    adapter = make_adapter()
    results = adapter.search("Mechatroniker", location="Hamburg", results_size=25)

    assert results == [SAMPLE_JOB]
    url, payload, headers = calls[0]
    assert url == "https://de.jooble.org/api/fake-jooble-key"
    assert payload["keywords"] == "Mechatroniker"
    assert payload["location"] == "Hamburg"
    assert payload["ResultOnPage"] == "25"
    # A default python-requests UA is a common, independent WAF/edge-block
    # trigger - see the domain-key root-cause note in jooble.py's module
    # docstring - so it must be set explicitly, not left to the default.
    assert "python-requests" not in headers["User-Agent"]


def test_optional_params_forwarded_when_provided(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        captured.update(json)
        return FakeResponse(200, {"totalCount": 0, "jobs": []})

    monkeypatch.setattr(requests, "post", fake_post)
    make_adapter().search("Mechatroniker", radius=40, salary=1000, companysearch=True)

    assert captured["radius"] == "40"
    assert captured["salary"] == 1000
    assert captured["companysearch"] == "true"


def test_empty_results_returns_empty_list(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(200, {"totalCount": 0, "jobs": []}))
    assert make_adapter().search("Mechatroniker") == []


def test_pagination_result_size_respected(monkeypatch):
    jobs = [dict(SAMPLE_JOB, id=i) for i in range(10)]
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(200, {"jobs": jobs}))
    results = make_adapter().search("Mechatroniker", results_size=5)
    assert len(results) == 5


def test_malformed_response_raises_adapter_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(200, malformed=True))
    with pytest.raises(JoobleAdapterError, match="malformed"):
        make_adapter().search("Mechatroniker")


def test_unexpected_response_shape_raises_adapter_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(200, {"unexpected": "shape"}))
    with pytest.raises(JoobleAdapterError, match="unexpected response shape"):
        make_adapter().search("Mechatroniker")


def test_401_raises_api_key_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(401))
    with pytest.raises(JoobleAdapterError, match="rejected the configured API key"):
        make_adapter().search("Mechatroniker")


def test_403_raises_api_key_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(403))
    with pytest.raises(JoobleAdapterError, match="rejected the configured API key"):
        make_adapter().search("Mechatroniker")


def test_429_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(429))
    with pytest.raises(JoobleAdapterError, match="rate limit"):
        make_adapter().search("Mechatroniker")


def test_500_raises_generic_http_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: FakeResponse(500))
    with pytest.raises(JoobleAdapterError, match="HTTP 500"):
        make_adapter().search("Mechatroniker")


def test_timeout_raises_adapter_error(monkeypatch):
    def fake_post(*a, **kw):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(JoobleAdapterError, match="timed out"):
        make_adapter().search("Mechatroniker")


def test_connection_error_raises_adapter_error(monkeypatch):
    def fake_post(*a, **kw):
        raise requests.exceptions.ConnectionError("dns failed")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(JoobleAdapterError, match="Could not reach Jooble"):
        make_adapter().search("Mechatroniker")


def test_api_key_never_leaks_into_error_message(monkeypatch):
    def fake_post(*a, **kw):
        raise requests.exceptions.RequestException("failed for https://de.jooble.org/api/fake-jooble-key")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(JoobleAdapterError) as exc_info:
        make_adapter().search("Mechatroniker")
    assert "fake-jooble-key" not in str(exc_info.value)


def test_get_job_returns_none_no_detail_endpoint():
    assert make_adapter().get_job("987654321") is None


def test_normalize_maps_all_documented_fields():
    normalized = make_adapter().normalize(SAMPLE_JOB)
    assert normalized.source == "jooble"
    assert normalized.external_id == "987654321"
    assert normalized.title == "Ausbildung Mechatroniker"
    assert normalized.company_name == "Beispiel AG"
    assert normalized.location == "Hamburg"
    assert normalized.salary == "1.000 EUR"
    assert normalized.employment_type == "Vollzeit"
    assert normalized.description == "Wir suchen dich..."
    assert normalized.application_url == "https://de.jooble.org/jdp/987654321"
    assert normalized.source_url == "https://de.jooble.org/jdp/987654321"
    assert normalized.raw == SAMPLE_JOB


def test_normalize_does_not_fabricate_ausbildung_employment_type():
    raw = dict(SAMPLE_JOB, type=None)
    normalized = make_adapter().normalize(raw)
    assert normalized.employment_type is None


def test_normalize_handles_missing_optional_fields():
    minimal = {"id": 1, "title": "Some job"}
    normalized = make_adapter().normalize(minimal)
    assert normalized.company_name is None
    assert normalized.location is None
    assert normalized.salary is None
    assert normalized.description is None


def test_normalize_missing_title_falls_back_to_untitled():
    normalized = make_adapter().normalize({"id": 1})
    assert normalized.title == "Untitled posting"
