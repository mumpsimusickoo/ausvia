"""Tests for app/jobs/adapters/arbeitsagentur.py's normalize() - rewritten
this session against a REAL v6 search response and a real v4/jobdetails
response (job-source integration pass), not the old v4-only field names
(titel, arbeitgeber, arbeitsort, externeUrl, refnr) that don't exist in
v6's actual shape at all. SAMPLE_SEARCH_RESULT/SAMPLE_DETAIL below are
trimmed, anonymized copies of real captured responses (company/location
changed, everything else - field names and shapes - kept faithful).
"""
from app.jobs.adapters.arbeitsagentur import ArbeitsagenturAdapter

SAMPLE_SEARCH_RESULT = {
    "stellenangebotsart": "AUSBILDUNG",
    "ausbildungsart": "AUSBILDUNG",
    "stellenangebotsTitel": "Elektroniker (m/w/d)",
    "eintrittszeitraum": {"von": "2027-09-01"},
    "verguetungsangabe": "KEINE_ANGABEN",
    "vertragsdauer": "KEINE_ANGABE",
    "stellenlokationen": [
        {
            "adresse": {"plz": "88400", "ort": "Musterstadt", "region": "BADEN_WUERTTEMBERG", "land": "DEUTSCHLAND"},
            "breite": 48.0898433,
            "laenge": 9.7852486,
        }
    ],
    "veroeffentlichungszeitraum": {"von": "2026-08-13"},
    "datumErsteVeroeffentlichung": "2026-08-13",
    "aenderungsdatum": "2026-08-13T07:02:33.177",
    "externeURL": "https://example.com/jobmanager-arbeitsagentur/124517118",
    "hauptberuf": "Elektroniker/in - Geräte und Systeme",
    "firma": "MUSTER WERKE Maschinenfabrik GmbH",
    "referenznummer": "12511-2025X0000046303-S",
    "alleBerufe": ["Elektroniker/in - Geräte und Systeme"],
}

SAMPLE_DETAIL = dict(
    SAMPLE_SEARCH_RESULT,
    stellenangebotsBeschreibung="MEHR ALS DU DENKST\n\nAbwechslungsreiche Tätigkeiten...",
    geforderterBildungsabschluss="NICHT_RELEVANT",
)


def make_adapter():
    return ArbeitsagenturAdapter()


def test_normalize_maps_real_v6_search_fields():
    normalized = make_adapter().normalize(SAMPLE_SEARCH_RESULT)
    assert normalized.source == "arbeitsagentur"
    assert normalized.external_id == "12511-2025X0000046303-S"
    assert normalized.title == "Elektroniker (m/w/d)"
    assert normalized.company_name == "MUSTER WERKE Maschinenfabrik GmbH"
    assert normalized.location == "Musterstadt"
    assert normalized.federal_state == "BADEN_WUERTTEMBERG"
    assert normalized.postal_code == "88400"
    assert normalized.start_date == "2027-09-01"
    assert normalized.application_url == "https://example.com/jobmanager-arbeitsagentur/124517118"
    assert normalized.source_url == "https://example.com/jobmanager-arbeitsagentur/124517118"


def test_normalize_treats_no_info_enum_values_as_none_not_literal_text():
    # "KEINE_ANGABEN" is Bundesagentur's own "not specified" enum, not a
    # real value - must never be shown to a user as if it were a real salary.
    normalized = make_adapter().normalize(SAMPLE_SEARCH_RESULT)
    assert normalized.salary is None


def test_normalize_without_detail_has_no_description():
    # The search response alone never carries a description (confirmed
    # against the real API - it's jobdetails-only) - this must stay honest
    # (None), not silently blank/fabricated.
    normalized = make_adapter().normalize(SAMPLE_SEARCH_RESULT)
    assert normalized.description is None


def test_normalize_with_merged_detail_fills_in_description():
    merged_raw = {**SAMPLE_SEARCH_RESULT, "_detail": SAMPLE_DETAIL}
    normalized = make_adapter().normalize(merged_raw)
    assert normalized.description.startswith("MEHR ALS DU DENKST")


def test_normalize_treats_nicht_relevant_education_as_none():
    merged_raw = {**SAMPLE_SEARCH_RESULT, "_detail": SAMPLE_DETAIL}
    normalized = make_adapter().normalize(merged_raw)
    assert normalized.education_requirements is None


def test_normalize_real_education_value_is_preserved():
    detail = dict(SAMPLE_DETAIL, geforderterBildungsabschluss="MITTLERER_BILDUNGSABSCHLUSS")
    merged_raw = {**SAMPLE_SEARCH_RESULT, "_detail": detail}
    normalized = make_adapter().normalize(merged_raw)
    assert normalized.education_requirements == "MITTLERER_BILDUNGSABSCHLUSS"


def test_normalize_handles_missing_locations_array():
    raw = {**SAMPLE_SEARCH_RESULT, "stellenlokationen": []}
    normalized = make_adapter().normalize(raw)
    assert normalized.location is None
    assert normalized.postal_code is None


def test_normalize_missing_title_falls_back_to_hauptberuf():
    raw = dict(SAMPLE_SEARCH_RESULT)
    del raw["stellenangebotsTitel"]
    normalized = make_adapter().normalize(raw)
    assert normalized.title == "Elektroniker/in - Geräte und Systeme"


def test_normalize_missing_everything_falls_back_to_untitled():
    normalized = make_adapter().normalize({"referenznummer": "X-1"})
    assert normalized.title == "Untitled posting"


def test_employment_type_always_ausbildung():
    # Unlike Adzuna/Jooble, this source's angebotsart=4 filter genuinely
    # guarantees apprenticeship-only results - the "Ausbildung" default is
    # a confirmed fact here, not a fabrication.
    normalized = make_adapter().normalize(SAMPLE_SEARCH_RESULT)
    assert normalized.employment_type == "Ausbildung"
