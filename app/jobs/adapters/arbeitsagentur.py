"""
Adapter wrapping jobsearch.py, the client for the Bundesagentur für Arbeit's
Jobsuche interface (not an officially published API - see jobsearch.py's
module docstring for the full correction). Field names below match a real
v6 search response and a real v4/jobdetails response captured live this
session (job-source integration pass) - not the old v4-only field names
(titel, arbeitgeber, arbeitsort, externeUrl, refnr) this file used before,
which don't exist in v6's actual response shape at all. If the API changes
shape again, this is the one place to update.
"""
from datetime import date, datetime

import jobsearch
from app.jobs.adapters.base import JobSourceAdapter, NormalizedJob

# Bundesagentur uses these literal enum strings to mean "no information
# given" rather than omitting the field - showing them to a user as if they
# were real values ("Salary: KEINE_ANGABEN") would be worse than showing
# nothing, so they're treated as absent, not fabricated as real values but
# also not silently kept as-is.
_NO_INFO_VALUES = {"KEINE_ANGABEN", "KEINE_ANGABE", "NICHT_RELEVANT"}


def _first(raw, *keys):
    for key in keys:
        value = raw.get(key)
        if value:
            return value
    return None


def _clean(value):
    return None if not value or value in _NO_INFO_VALUES else value


def _parse_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _primary_location(raw):
    """stellenlokationen is an array (a posting can list more than one
    site) - the first entry is used as the canonical location, matching
    how every other field here treats a posting as having one location."""
    locations = raw.get("stellenlokationen") or []
    if not locations or not isinstance(locations, list):
        return {}
    return locations[0].get("adresse") or {}


class ArbeitsagenturAdapter(JobSourceAdapter):
    source_name = "arbeitsagentur"
    display_name = "Bundesagentur für Arbeit (Jobsuche)"

    def search(self, keywords, location=None, **kwargs):
        return jobsearch.search_ausbildung(keywords=keywords, location=location, **kwargs)

    def get_job(self, external_id):
        try:
            return jobsearch.get_job_detail(external_id)
        except Exception:
            return None

    def normalize(self, raw):
        # Optional: caller may merge get_job()'s detail response in under
        # "_detail" before normalizing, to fill in fields (description,
        # education requirements) the search response alone doesn't carry.
        detail = raw.get("_detail") or {}
        merged = {**raw, **detail}
        adresse = _primary_location(merged)

        return NormalizedJob(
            source=self.source_name,
            external_id=merged.get("referenznummer"),
            source_url=merged.get("externeURL"),
            title=_first(merged, "stellenangebotsTitel", "hauptberuf") or "Untitled posting",
            company_name=merged.get("firma"),
            location=adresse.get("ort"),
            federal_state=adresse.get("region"),
            postal_code=adresse.get("plz"),
            start_date=(merged.get("eintrittszeitraum") or {}).get("von"),
            application_deadline=None,  # no deadline field observed in real search/detail responses
            salary=_clean(merged.get("verguetungsangabe")),
            employment_type="Ausbildung",
            description=merged.get("stellenangebotsBeschreibung"),
            requirements=None,  # no distinct free-text requirements field observed
            education_requirements=_clean(merged.get("geforderterBildungsabschluss")),
            contact_person=self._contact_name(detail),
            contact_email=self._contact_email(detail),
            application_url=merged.get("externeURL"),
            raw=raw,
        )

    @staticmethod
    def _contact_name(detail):
        # Not observed in any real response sampled this session (contact
        # info may simply not be exposed on this interface at all) - kept
        # defensively in case a posting ever does carry it, per the
        # community documentation's field list.
        contact = detail.get("kontaktdaten") or detail.get("ansprechpartner") or {}
        if isinstance(contact, dict):
            name = " ".join(p for p in [contact.get("vorname"), contact.get("nachname")] if p)
            return name or None
        return None

    @staticmethod
    def _contact_email(detail):
        contact = detail.get("kontaktdaten") or detail.get("ansprechpartner") or {}
        if isinstance(contact, dict):
            return contact.get("email")
        return None

    def check_availability(self, external_id):
        try:
            detail = self.get_job(external_id)
        except Exception:
            return None
        if detail is None:
            return False
        return True
