"""Adapter for the Jooble REST API (official - see jooble.org/api/about).
The API key is manually issued after submitting a request form (name,
role, email, website) - not instant self-serve like Adzuna's, so allow
lead time before this adapter can actually be enabled. Endpoint/request/
response shape below match the current REST API documentation at
help.jooble.org.

Terms-of-service note: jooble.org/info/terms (the public site ToS, read
directly, not assumed) prohibits bots/crawlers against the *website* and
says nothing API-specific - it does not separately publish API usage
terms. The terms actually governing API use are presented during the
manual key-request process, which needs a human to complete (real
name/role/contact info) - this couldn't be resolved or assumed as part of
this implementation pass. See JOB_SOURCES.md.
"""
import logging

import requests

from app.jobs.adapters.base import JobSourceAdapter, NormalizedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://jooble.org/api"
REQUEST_TIMEOUT = 20


class JoobleAdapterError(Exception):
    """Raised for any Jooble failure (network, HTTP, malformed response) -
    caught by app/jobs/ingest.py, which isolates one provider's failure
    from the others."""


class JoobleAdapter(JobSourceAdapter):
    source_name = "jooble"
    display_name = "Jooble"

    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, keywords, location=None, page=1, results_size=25, radius=None, salary=None,
               companysearch=None, **kwargs):
        """keywords/location/radius/page/results_size/salary/companysearch
        map directly to Jooble's own documented POST body fields - no
        invented parameters. One HTTP call per search() call (Jooble's API
        is one page per request, unlike Adzuna's - no internal pagination
        loop needed to satisfy a single results_size)."""
        payload = {"keywords": keywords, "page": str(page), "ResultOnPage": str(results_size)}
        if location:
            payload["location"] = location
        if radius is not None:
            payload["radius"] = str(radius)
        if salary is not None:
            payload["salary"] = salary
        if companysearch is not None:
            payload["companysearch"] = str(bool(companysearch)).lower()

        data = self._request(payload)
        jobs = data.get("jobs")
        if not isinstance(jobs, list):
            raise JoobleAdapterError("Jooble returned an unexpected response shape.")
        return jobs[:results_size]

    def _request(self, payload):
        try:
            resp = requests.post(f"{BASE_URL}/{self.api_key}", json=payload, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout as e:
            raise JoobleAdapterError("Jooble request timed out.") from e
        except requests.exceptions.ConnectionError as e:
            raise JoobleAdapterError("Could not reach Jooble.") from e
        except requests.exceptions.RequestException as e:
            # Never let the raw exception (which can echo the request URL,
            # containing the API key, in its str()) reach a caller.
            raise JoobleAdapterError("Jooble request failed.") from e

        if resp.status_code in (401, 403):
            raise JoobleAdapterError("Jooble rejected the configured API key.")
        if resp.status_code == 429:
            raise JoobleAdapterError("Jooble rate limit exceeded.")
        if resp.status_code >= 400:
            raise JoobleAdapterError(f"Jooble returned HTTP {resp.status_code}.")

        try:
            return resp.json()
        except ValueError as e:
            raise JoobleAdapterError("Jooble returned a malformed (non-JSON) response.") from e

    def get_job(self, external_id):
        # No documented get-by-id endpoint - search results already carry
        # everything Jooble exposes for a listing.
        return None

    def normalize(self, raw):
        return NormalizedJob(
            source=self.source_name,
            external_id=str(raw["id"]) if raw.get("id") is not None else None,
            source_url=raw.get("link"),
            title=raw.get("title") or "Untitled posting",
            company_name=raw.get("company"),
            location=raw.get("location"),
            salary=raw.get("salary") or None,
            # Deliberately NOT defaulted to "Ausbildung" - same reasoning as
            # AdzunaAdapter: Jooble's "type" field (full-time/part-time/...)
            # doesn't confirm an apprenticeship, and Jooble keyword search
            # doesn't guarantee apprenticeship-only results either. See
            # JOB_SOURCES.md for the live-tested result-quality finding.
            employment_type=raw.get("type") or None,
            description=raw.get("snippet"),
            application_url=raw.get("link"),
            raw=raw,
        )
