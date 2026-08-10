"""
Client for the Bundesagentur fuer Arbeit ("Jobsuche") public job search API.
This is the official, free, public API behind arbeitsagentur.de/jobsuche.
No account/key needed beyond the well-known public API key used by their
own web frontend.
"""
import requests

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
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

        stellen = data.get("stellenangebote", [])
        if not stellen:
            break

        all_results.extend(stellen)
        page += 1

        # stop if we've fetched all pages the API reports
        max_results = data.get("maxErgebnisse", 0)
        if page * page_size > max_results:
            break

    return all_results[:results_size]


def get_job_detail(refnr):
    """Fetch full detail (incl. description, contact info) for one posting by reference number."""
    url = f"https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{refnr}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def simplify_posting(raw):
    """Extract the fields we actually need from a raw search-result posting."""
    return {
        "refnr": raw.get("refnr"),
        "title": raw.get("titel"),
        "company": raw.get("arbeitgeber"),
        "location": (raw.get("arbeitsort") or {}).get("ort"),
        "publish_date": raw.get("aktuelleVeroeffentlichungsdatum"),
        "external_url": raw.get("externeUrl"),  # present if it's hosted on employer's own site
    }
