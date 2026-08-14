"""Tests for jobsearch.py's two real bugs found and fixed this session
(job-source integration pass), both confirmed against the live API before
being treated as bugs, not assumed:

1. search_ausbildung() read data["stellenangebote"] - v6's actual key is
   "ergebnisliste". A naive v4->v6 URL bump alone would have silently
   returned zero results forever, indistinguishable from "still blocked."
2. get_job_detail() passed the reference number to /v4/jobdetails/{refnr}
   raw - the API requires it base64-encoded, silently 404ing
   ("STELLENANGEBOT_NICHT_GEFUNDEN") otherwise rather than erroring loudly.
"""
import base64

import requests

import jobsearch


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}")


def test_search_ausbildung_reads_ergebnisliste_not_stellenangebote(monkeypatch):
    posting = {"referenznummer": "X-1", "stellenangebotsTitel": "Elektroniker"}

    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResponse({"ergebnisliste": [posting], "maxErgebnisse": 1})

    monkeypatch.setattr(requests, "get", fake_get)
    results = jobsearch.search_ausbildung("Elektroniker", results_size=10)
    assert results == [posting]


def test_search_ausbildung_ignores_old_v4_key_name(monkeypatch):
    # A response shaped like the OLD v4 schema (no "ergebnisliste") must
    # come back empty, not error - proves the code really reads the new
    # key, not both/either.
    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResponse({"stellenangebote": [{"refnr": "old-shape"}], "maxErgebnisse": 1})

    monkeypatch.setattr(requests, "get", fake_get)
    results = jobsearch.search_ausbildung("Elektroniker", results_size=10)
    assert results == []


def test_search_ausbildung_paginates_until_max_ergebnisse(monkeypatch):
    call_count = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        call_count["n"] += 1
        page = params["page"]
        if page == 1:
            return FakeResponse({"ergebnisliste": [{"referenznummer": f"X-{i}"} for i in range(25)], "maxErgebnisse": 30})
        return FakeResponse({"ergebnisliste": [{"referenznummer": f"X-{i}"} for i in range(25, 30)], "maxErgebnisse": 30})

    monkeypatch.setattr(requests, "get", fake_get)
    results = jobsearch.search_ausbildung("Elektroniker", results_size=30)
    assert len(results) == 30
    assert call_count["n"] == 2


def test_search_ausbildung_uses_v6_url(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        return FakeResponse({"ergebnisliste": [], "maxErgebnisse": 0})

    monkeypatch.setattr(requests, "get", fake_get)
    jobsearch.search_ausbildung("Elektroniker")
    assert captured["url"] == "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"


def test_get_job_detail_base64_encodes_the_reference_number(monkeypatch):
    refnr = "12511-2025X0000046303-S"
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        return FakeResponse({"referenznummer": refnr})

    monkeypatch.setattr(requests, "get", fake_get)
    jobsearch.get_job_detail(refnr)

    expected_encoded = base64.b64encode(refnr.encode()).decode()
    assert expected_encoded in captured["url"]
    assert refnr not in captured["url"]  # the raw refnr must NOT appear un-encoded
    assert captured["url"].startswith(
        "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"
    )


def test_get_job_detail_returns_parsed_json(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse({"stellenangebotsTitel": "Elektroniker"}))
    detail = jobsearch.get_job_detail("X-1")
    assert detail == {"stellenangebotsTitel": "Elektroniker"}
