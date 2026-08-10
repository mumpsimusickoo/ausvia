"""
Adapter wrapping jobsearch.py, the existing client for the Bundesagentur für
Arbeit's public Jobsuche API (official, free, no account required - see
jobsearch.py's module docstring). Field names below match the public API as
last confirmed; if the API changes shape, this is the one place to update.
"""
from datetime import date, datetime

import jobsearch
from app.jobs.adapters.base import JobSourceAdapter, NormalizedJob


def _first(raw, *keys):
    for key in keys:
        value = raw.get(key)
        if value:
            return value
    return None


def _parse_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


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
        arbeitsort = raw.get("arbeitsort") or {}
        detail = raw.get("_detail") or {}  # optional: caller may merge in get_job() output before normalizing

        return NormalizedJob(
            source=self.source_name,
            external_id=raw.get("refnr"),
            source_url=raw.get("externeUrl"),
            title=_first(raw, "titel", "beruf") or "Untitled posting",
            company_name=_first(raw, "arbeitgeber", "arbeitgeberName"),
            location=arbeitsort.get("ort"),
            federal_state=arbeitsort.get("region") or arbeitsort.get("bundesland"),
            postal_code=arbeitsort.get("plz"),
            start_date=_first(detail, "eintrittsdatum", "startdatum") or raw.get("eintrittsdatum"),
            application_deadline=_parse_date(_first(detail, "bewerbungsfrist", "bewerbungsschluss")),
            salary=_first(detail, "verguetung", "vergütung"),
            employment_type="Ausbildung",
            description=_first(detail, "stellenbeschreibung", "beschreibung"),
            requirements=_first(detail, "anforderungen"),
            education_requirements=_first(detail, "ausbildungsvoraussetzung"),
            contact_person=self._contact_name(detail),
            contact_email=self._contact_email(detail),
            application_url=raw.get("externeUrl"),
            raw=raw,
        )

    @staticmethod
    def _contact_name(detail):
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
