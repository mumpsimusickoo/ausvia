"""Optional, manual integration tests against the REAL provider APIs - not
run as part of the normal test suite (no network access, no real
credentials, ever, by default). Opt in explicitly:

    RUN_LIVE_PROVIDER_TESTS=1 pytest tests/test_live_providers.py -v -s

Arbeitsagentur needs no credentials (see jobsearch.py) but is still gated
behind the same opt-in flag, so a plain `pytest` run never touches the
network for it either. Adzuna/Jooble additionally need real credentials in
the environment (ADZUNA_APP_ID/ADZUNA_APP_KEY, JOOBLE_API_KEY) - never put
real credentials in this file or anywhere in the repo; export them in your
shell before running.

Each test prints what it actually found (result count, a sample title/
company) with -s so a human can judge real result quality - notably
whether Adzuna/Jooble keyword search for German Ausbildung terms returns
genuine apprenticeship postings or mostly unrelated general listings, the
open question this pass was specifically asked to test for real.
"""
import os

import pytest

from app.jobs.adapters.adzuna import AdzunaAdapter
from app.jobs.adapters.arbeitsagentur import ArbeitsagenturAdapter
from app.jobs.adapters.jooble import JoobleAdapter

LIVE = os.environ.get("RUN_LIVE_PROVIDER_TESTS") == "1"
ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY")
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY")

skip_unless_live = pytest.mark.skipif(not LIVE, reason="set RUN_LIVE_PROVIDER_TESTS=1 to run live provider tests")
skip_unless_adzuna_configured = pytest.mark.skipif(
    not (LIVE and ADZUNA_APP_ID and ADZUNA_APP_KEY),
    reason="set RUN_LIVE_PROVIDER_TESTS=1 plus ADZUNA_APP_ID/ADZUNA_APP_KEY to run this",
)
skip_unless_jooble_configured = pytest.mark.skipif(
    not (LIVE and JOOBLE_API_KEY),
    reason="set RUN_LIVE_PROVIDER_TESTS=1 plus JOOBLE_API_KEY to run this",
)


@skip_unless_live
def test_arbeitsagentur_live_search():
    adapter = ArbeitsagenturAdapter()
    results = adapter.search("Elektroniker", results_size=10)
    print(f"\nArbeitsagentur: {len(results)} result(s) for 'Elektroniker'")
    if results:
        normalized = adapter.normalize(results[0])
        print(f"  sample: {normalized.title!r} @ {normalized.company_name!r} ({normalized.location})")
    assert isinstance(results, list)


@skip_unless_adzuna_configured
def test_adzuna_live_search_ausbildung_result_quality():
    adapter = AdzunaAdapter(app_id=ADZUNA_APP_ID, app_key=ADZUNA_APP_KEY, country="de")
    results = adapter.search("Ausbildung Elektroniker", results_size=25)
    print(f"\nAdzuna: {len(results)} result(s) for 'Ausbildung Elektroniker'")
    apprenticeship_like = 0
    for raw in results:
        normalized = adapter.normalize(raw)
        title_lower = (normalized.title or "").lower()
        is_apprenticeship_like = any(w in title_lower for w in ("ausbildung", "azubi", "auszubildende"))
        apprenticeship_like += is_apprenticeship_like
        print(f"  - {normalized.title!r} @ {normalized.company_name!r} [{'APPRENTICESHIP-LIKE' if is_apprenticeship_like else 'general listing'}]")
    if results:
        print(f"  {apprenticeship_like}/{len(results)} titles look apprenticeship-related by keyword match alone.")
    assert isinstance(results, list)


@skip_unless_jooble_configured
def test_jooble_live_search_ausbildung_result_quality():
    adapter = JoobleAdapter(api_key=JOOBLE_API_KEY)
    results = adapter.search("Ausbildung Elektroniker", location="Deutschland", results_size=25)
    print(f"\nJooble: {len(results)} result(s) for 'Ausbildung Elektroniker'")
    apprenticeship_like = 0
    for raw in results:
        normalized = adapter.normalize(raw)
        title_lower = (normalized.title or "").lower()
        is_apprenticeship_like = any(w in title_lower for w in ("ausbildung", "azubi", "auszubildende"))
        apprenticeship_like += is_apprenticeship_like
        print(f"  - {normalized.title!r} @ {normalized.company_name!r} [{'APPRENTICESHIP-LIKE' if is_apprenticeship_like else 'general listing'}]")
    if results:
        print(f"  {apprenticeship_like}/{len(results)} titles look apprenticeship-related by keyword match alone.")
    assert isinstance(results, list)
