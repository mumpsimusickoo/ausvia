"""
Client for the Bundesagentur fuer Arbeit ("Jobsuche") job search API.

Correction: this is NOT an official API. Confirmed via bundesAPI/
jobsuche-api (the current community documentation of this exact endpoint):
Bundesagentur fuer Arbeit has never published a developer API for this
data. What this client calls is the internal endpoint the
arbeitsagentur.de website's own frontend uses - API_KEY below is that
frontend's own static key, reverse-engineered and documented by the
community, not a per-developer credential to register for. There's no
more-official alternative; this is the one access method that exists, and
it's implemented here exactly as currently documented.

MAJOR UPDATE (job-source integration pass), live-verified, not assumed:
earlier sessions confirmed v4 (/pc/v4/jobs) returns a blank HTTP 403 from
every network tried, and treated that as a settled, version-independent
anti-automation block. Re-tested this session while bumping to the
currently-documented v6 search endpoint for version currency - and v6
(/pc/v6/jobs) returned real HTTP 200 responses with genuine job data, from
the same network, same X-API-Key value, in the same test run where v4
*still* 403'd 3/3 times back-to-back. A request to v6 with no key or a
deliberately wrong key still 403'd, confirming the key is being validated
normally on v6, not just ignored. Full job detail via
/pc/v4/jobdetails/{base64(refnr)} also succeeded once the reference number
was correctly base64-encoded (get_job_detail() below never did this
before - a separate, real bug, independent of the v4/v6 question, that
silently 404'd every detail lookup even on a network where search worked).

This does not prove the endpoint is reliably open everywhere or forever -
only that from this specific network, at this specific time, v6 (unlike
v4) was not blocked. The original 403 finding came from multiple networks
including a residential ISP connection; this new v6 result has only been
seen from one network so far and needs re-verification from the actual
production environment before being treated as durably fixed. See
JOB_SOURCES.md for the full, current state of this finding.

v6's response schema is meaningfully different from v4's, not just the
URL - field names below (ergebnisliste, stellenangebotsTitel, firma,
referenznummer, stellenlokationen, externeURL, etc.) come from real
observed v6/v4-jobdetails responses this session, not the old v4 field
names (stellenangebote, titel, arbeitgeber, arbeitsort, externeUrl) a
naive URL-only bump would have kept silently using.
"""
import base64

import requests

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
API_KEY = "jobboerse-jobsuche"  # public key used by the official web frontend

HEADERS = {"X-API-Key": API_KEY}


def search_ausbildung(keywords, location=None, radius=200, results_size=50):
    """
    Search for Ausbildung (apprenticeship) postings.

    keywords: string, e.g. "Elektroniker Automatisierungstechnik"
    location: optional city/PLZ string. If None, searches all of Germany.
    radius: search radius in km around location (ignored if location is None)
    results_size: max number of results to fetch (API paginates in pages of ~25)
    """
    all_results = []
    page = 1
    page_size = 25

    while len(all_results) < results_size:
        params = {
            "was": keywords,
            "angebotsart": 4,  # 4 = Ausbildung/Duales Studium
            "page": page,
            "size": page_size,
        }
        if location:
            params["wo"] = location
            params["umkreis"] = radius

        resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        # v6's result array is "ergebnisliste" - v4 used "stellenangebote".
        # Confirmed via a real live v6 response this session, not assumed.
        postings = data.get("ergebnisliste", [])
        if not postings:
            break

        all_results.extend(postings)
        page += 1

        # stop once we've fetched all results the API reports exist.
        # (Pre-existing bug fixed this session: the old check here compared
        # page * page_size - the *next* page's cumulative slice - against
        # max_results, which stops one full page too early whenever
        # max_results isn't an exact multiple of page_size, e.g. 30 total
        # at page_size=25 stopped after page 1's 25 and never fetched the
        # remaining 5. Never noticed before since this endpoint was always
        # 403ing before v6.)
        max_results = data.get("maxErgebnisse", 0)
        if len(all_results) >= max_results:
            break

    return all_results[:results_size]


def get_job_detail(refnr):
    """Fetch full detail (incl. description) for one posting by reference
    number. The API requires the reference number base64-encoded in the
    URL path (per jobsuche.api.bund.dev's documented workflow) - passing it
    raw silently 404s ("STELLENANGEBOT_NICHT_GEFUNDEN") rather than
    erroring loudly, which is why this went unnoticed until live-verified
    this session."""
    encoded_refnr = base64.b64encode(refnr.encode()).decode()
    url = f"https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{encoded_refnr}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()
