"""Adapter for the Adzuna Job Search API (official, https://developer.adzuna.com/).
Free access is a 14-day trial only ("strictly for the purpose of validating
the general coverage and quality of the data... in addition to usability
testing" - Adzuna's Terms of Service), not indefinite free use - continued
production use needs a licence agreement directly with Adzuna. See
JOB_SOURCES.md for the trial-window tracking; this adapter being built and
working is not the same thing as being cleared for ongoing production use.

Attribution requirement (ToS, read directly, not assumed): displaying
Adzuna listings must show a "Jobs by Adzuna" credit - "Jobs" hyperlinked to
Adzuna, at least 116x23px, with the Adzuna logo also hyperlinked. Rendered
in app/templates/jobs/_source_attribution.html wherever a listing's
sources include "adzuna" - not removable/optional per the terms.

Default rate limits as currently documented: 25 hits/minute, 250/day,
1,000/week, 2,500/month (re-confirm against developer.adzuna.com directly
before relying on this - limits change). This adapter makes at most one
HTTP call per search() call under the default results_size (one Adzuna
page), and app/jobs/ingest.py's per-query cache additionally avoids
re-hitting Adzuna for a repeated identical search within its TTL window.
"""
import logging

import requests

from app.jobs.adapters.base import JobSourceAdapter, NormalizedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_RESULTS_PER_PAGE = 25
REQUEST_TIMEOUT = 20


class AdzunaAdapterError(Exception):
    """Raised for any Adzuna failure (network, HTTP, malformed response) -
    caught by app/jobs/ingest.py, which isolates one provider's failure
    from the others (never lets one broken source break a whole search)."""


class AdzunaAdapter(JobSourceAdapter):
    source_name = "adzuna"
    display_name = "Adzuna"

    def __init__(self, app_id, app_key, country="de"):
        self.app_id = app_id
        self.app_key = app_key
        self.country = country

    def search(self, keywords, location=None, page=1, results_size=25, **kwargs):
        """keywords: free-text query (e.g. "Ausbildung Elektroniker").
        location: optional city/region string - passed through to Adzuna's
        own "where" filter rather than emulated locally, per the "use
        provider filters where supported" requirement. results_size: capped
        to a small number of real HTTP calls per search on purpose - see
        module docstring on rate limits."""
        results = []
        remaining = results_size
        current_page = page

        while remaining > 0:
            page_size = min(remaining, DEFAULT_RESULTS_PER_PAGE)
            params = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "what": keywords,
                "results_per_page": page_size,
                "content-type": "application/json",
            }
            if location:
                params["where"] = location

            data = self._request(current_page, params)
            page_results = data.get("results")
            if not isinstance(page_results, list):
                raise AdzunaAdapterError("Adzuna returned an unexpected response shape.")
            if not page_results:
                break

            results.extend(page_results)
            remaining -= len(page_results)
            current_page += 1

            if len(page_results) < page_size:
                break  # fewer results than requested = last page

        return results[:results_size]

    def _request(self, page, params):
        try:
            resp = requests.get(f"{BASE_URL}/{self.country}/search/{page}", params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout as e:
            raise AdzunaAdapterError("Adzuna request timed out.") from e
        except requests.exceptions.ConnectionError as e:
            raise AdzunaAdapterError("Could not reach Adzuna.") from e
        except requests.exceptions.RequestException as e:
            # Never let the raw exception (which can echo back request
            # params, including app_key, in its str()) reach a caller.
            raise AdzunaAdapterError("Adzuna request failed.") from e

        if resp.status_code in (401, 403):
            raise AdzunaAdapterError("Adzuna rejected the configured credentials.")
        if resp.status_code == 429:
            raise AdzunaAdapterError("Adzuna rate limit exceeded.")
        if resp.status_code >= 400:
            raise AdzunaAdapterError(f"Adzuna returned HTTP {resp.status_code}.")

        try:
            return resp.json()
        except ValueError as e:
            raise AdzunaAdapterError("Adzuna returned a malformed (non-JSON) response.") from e

    def get_job(self, external_id):
        # No documented get-by-id endpoint - Adzuna's search results already
        # carry everything this adapter can normalize (description,
        # salary, redirect_url), unlike Arbeitsagentur's separate detail step.
        return None

    def normalize(self, raw):
        location = raw.get("location") or {}
        company = raw.get("company") or {}

        return NormalizedJob(
            source=self.source_name,
            external_id=str(raw["id"]) if raw.get("id") is not None else None,
            source_url=raw.get("redirect_url"),
            title=raw.get("title") or "Untitled posting",
            company_name=company.get("display_name"),
            location=location.get("display_name"),
            salary=self._format_salary(raw.get("salary_min"), raw.get("salary_max")),
            # Deliberately NOT defaulted to "Ausbildung" (NormalizedJob's
            # dataclass default) - Adzuna's contract_type is a generic
            # full_time/part_time/contract label, not an apprenticeship
            # filter the way Arbeitsagentur's angebotsart=4 is. Adzuna
            # keyword search for "Ausbildung" surfaces a real mix of actual
            # apprenticeships and unrelated general listings that merely
            # mention the word - labeling every result "Ausbildung" would
            # fabricate a fact this source doesn't actually confirm. See
            # JOB_SOURCES.md for the live-tested result-quality finding.
            employment_type=raw.get("contract_type"),
            description=raw.get("description"),
            application_url=raw.get("redirect_url"),
            raw=raw,
        )

    @staticmethod
    def _format_salary(salary_min, salary_max):
        if not salary_min and not salary_max:
            return None
        if salary_min and salary_max and salary_min != salary_max:
            return f"{salary_min:.0f}–{salary_max:.0f}"
        return f"{salary_min or salary_max:.0f}"
