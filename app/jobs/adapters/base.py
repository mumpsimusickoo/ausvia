"""
JobSourceAdapter interface (spec section 10/11). Every job source - an official
API, a manual import, a future integration - implements this same shape so the
rest of the app (ingestion, dedup, search) never needs to know which source
a job came from.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass
class NormalizedJob:
    """Common internal job schema every adapter normalizes into."""

    source: str
    title: str
    external_id: str | None = None
    source_url: str | None = None
    company_name: str | None = None
    location: str | None = None
    federal_state: str | None = None
    postal_code: str | None = None
    start_date: str | None = None
    application_deadline: date | None = None
    salary: str | None = None
    employment_type: str | None = "Ausbildung"
    description: str | None = None
    requirements: str | None = None
    language_requirements: list | None = None
    skills: list | None = None
    education_requirements: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    application_url: str | None = None
    raw: dict = field(default_factory=dict)


class JobSourceAdapter(ABC):
    source_name: str
    display_name: str

    @abstractmethod
    def search(self, keywords, location=None, **kwargs):
        """Returns a list of raw (source-specific) job dicts."""

    @abstractmethod
    def get_job(self, external_id):
        """Fetches full detail for one posting. Returns a raw dict or None if not found."""

    @abstractmethod
    def normalize(self, raw):
        """Converts one raw job dict into a NormalizedJob."""

    def check_availability(self, external_id):
        """Best-effort: True if the posting still appears live, False if confirmed
        gone, None if the source can't tell us. Default: unknown."""
        return None
