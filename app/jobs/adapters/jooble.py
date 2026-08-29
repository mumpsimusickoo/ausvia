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

Domain-key root cause (found 2026-08-29, see DECISIONS.md): a Jooble API
key is issued per regional domain, not global - a jooble.org (US) key
against jooble.org's own endpoint returns a consistent 403 regardless of
headers/IP. The fix is BASE_URL pointing at the same regional domain the
key was actually issued for (de.jooble.org, confirmed live: 200, real
German Ausbildung listings) - not a workaround, the correct endpoint for
a German-region key. An explicit browser-like User-Agent is set below
too, kept even though the domain switch alone may have been sufficient -
a default `python-requests/x.x` UA is a common, independent trigger for
edge/WAF blocks.

Admin-only scoping (2026-08-29): Jooble's free tier is a LIFETIME cap of
500 requests per key - no reset, only a new key. This budget is reserved
for the maintainer's own account, not spent on general invited-user
traffic - enforced at the call sites (app/jobs/ingest.py's
ingest_search(admin=...), app/jobs/routes.py's search(), app/main/
routes.py's landing()) via app/jobs/adapters/manager.py's
ADMIN_ONLY_SOURCES, not inside this adapter itself. record_jooble_request()
below tracks the cumulative count against that lifetime cap - see its own
docstring. DECISIONS.md has the full reasoning.
"""
import logging

import requests

from app.jobs.adapters.base import JobSourceAdapter, NormalizedJob

logger = logging.getLogger(__name__)

# de.jooble.org, not jooble.org - see module docstring's "Domain-key root
# cause" note. A key issued for one regional domain is rejected (403) by
# every other one, including the global jooble.org host.
BASE_URL = "https://de.jooble.org/api"
REQUEST_TIMEOUT = 20
# requests' own default ("python-requests/x.x") is a common, independent
# trigger for edge/WAF blocks - set explicitly rather than relying on it,
# even though the domain fix above may have been sufficient on its own.
REQUEST_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Jooble's documented free-tier limit: 500 requests, LIFETIME (not
# monthly/daily like every other metered source this app talks to) - once
# spent, there's no reset, only requesting a brand-new key. Warn well
# before actually hitting it: 50 remaining (~10% of the total budget)
# is enough runway that an admin logging in every few days - the expected
# usage pattern now that this is admin-only, not a source under constant
# general traffic - will see the warning at least a few times before
# exhaustion, not just once right before it happens.
JOOBLE_LIFETIME_BUDGET = 500
JOOBLE_WARNING_THRESHOLD = 50


def record_jooble_request():
    """Increments the persistent cumulative Jooble request counter
    (JobSourceSetting.request_count for source_name="jooble") - called by
    app/jobs/ingest.py's ingest_search() exactly once per REAL outbound
    call that reaches Jooble, i.e. after ProviderQueryCache's 15-minute
    cache-hit check has already passed (a cache hit never reaches this;
    it never touches the network at all). Counts every real attempt
    regardless of outcome - success, a 403, a timeout - not just
    successes: a request that actually reached Jooble's servers has
    already spent its lifetime cost whether or not it returned anything
    usable, and there's no documented way to distinguish "didn't count
    against the cap" failures from ones that did, so this counts
    conservatively rather than risk under-counting against a budget that
    can't be topped up.

    Logs a warning (SystemLog, category "job_source") once remaining
    budget drops to JOOBLE_WARNING_THRESHOLD or below, so it's visible on
    /admin's recent-activity feed - and the raw count/remaining is also
    shown directly as its own stat on that page (see app/admin/routes.py),
    not left for an admin to notice only via the log feed scrolling by.
    """
    from app.extensions import db
    from app.models.job import JobSourceSetting
    from app.utils.logging import log_event

    setting = JobSourceSetting.query.filter_by(source_name="jooble").first()
    if setting is None:
        setting = JobSourceSetting(source_name="jooble", display_name="Jooble")
        db.session.add(setting)
    setting.request_count = (setting.request_count or 0) + 1
    db.session.commit()

    remaining = JOOBLE_LIFETIME_BUDGET - setting.request_count
    if remaining <= JOOBLE_WARNING_THRESHOLD:
        log_event(
            "job_source",
            f"Jooble request budget low: {remaining} of {JOOBLE_LIFETIME_BUDGET} lifetime "
            f"requests remaining ({setting.request_count} used so far). This cap does not "
            f"reset - a new key will be needed once it's exhausted.",
            level="warning",
        )
    return setting.request_count


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
            resp = requests.post(
                f"{BASE_URL}/{self.api_key}", json=payload, timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": REQUEST_USER_AGENT},
            )
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
