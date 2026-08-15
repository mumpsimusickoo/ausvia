"""Tests for app/jobs/requirements_section.py's deterministic requirements-
section isolator (job-description extraction pass). Fixtures below are
real, publicly-posted Arbeitsagentur descriptions pulled live during the
investigation this was built from - no personal information, these are
employer-authored job postings. Kept close to verbatim (only trimmed for
length in a couple of cases) specifically because the real formatting
quirks (markdown headers, emoji, inline "Label: value" lines, bullet
styles) are exactly what the isolator has to survive.
"""
from app.jobs.requirements_section import extract_requirements_section

STUB_DESCRIPTION = """ZUKUNFT
ANPACKEN. Starte deine Ausbildung bei Zoth! Elektroniker (m/w/d)

Postalische Bewerbungen an:

Zoth GmbH & Co. KG
Dr.-Walter-Zoth-Allee 1
56479 Westernohe

Digitale Bewerbungen entweder unter:

www.zoth.de/karriere
oder an:
bewerbung@zoth.de
"""

# Real posting: curriculum ("Das erwartet Dich") lists SPS-Programmierung
# as something the apprenticeship teaches; the actual requirements section
# ("Das bringst Du mit") is separate and does not mention it - exactly the
# curriculum-vs-requirement trap this pass exists to avoid.
PFIZER_MECHATRONIKER = """Möchtest du in einem internationalen Unternehmen arbeiten?

Das erwartet Dich:

 - Vermittlung von mechanischen Kenntnissen

 - Erwerb von Kenntnissen der Elektronik (z.B. Analog- und Digitaltechnik)

 - Umgang mit der Steuer- und Regelungstechnik wie Pneumatik und SPS-Programmierung sowie Robotertechnik

Das bringst Du mit:

 - Ein guter Schulabschluss – eine mittlere Reife, Fachhochschulreife oder Abitur bilden die Grundlage für deinen Einstieg

 - Neugier und Begeisterung für Technik – insbesondere für Mathematik, Physik und technische Zusammenhänge

 - Technisches Verständnis und analytisches Denkvermögen, um komplexe Abläufe zu durchdringen

 - Sehr gute Deutschkenntnisse in Wort und Schrift

Das bieten wir Dir:

 - Sammle wertvolle Praxiserfahrungen: Von Beginn an bist du aktiv in reale Projekte eingebunden
"""

# Real posting: same trap, different wording - curriculum under "Kernpunkte
# der Ausbildung" mentions "Programmieren mechatronischer Systeme"; the
# real prerequisites are under a separate "Voraussetzungen..." heading.
SORG_MECHATRONIKER = """Die Mechatronik ist die Verbindung von Maschinenbau, Elektrotechnik und Informatik.

Ausbildung als Mechatroniker (m/w/d) Kernpunkte der Ausbildung:

 * Grundlagen der Metallbearbeitung
 * Grundlagen der Elektronik
 * Programmieren mechatronischer Systeme

Voraussetzungen, die du mitbringen solltest:

 * Mittlerer Schul- oder qualifizierender Mittelschulabschluss
 * Technisches Verständnis
 * Interesse an Mathematik und Physik
 * Farbsehtüchtigkeit

Bitte sende deine Bewerbung per E-Mail an: CAREER@SORG.DE
"""

# Real posting: "Deutsch" appears as a school-subject reference inside the
# requirements section itself, not a language-proficiency requirement.
VERGOELST_EINZELHANDEL = """Du hast Spaß am direkten Kundenkontakt?

Was solltest du mitbringen?

• Lust auf direkten Kundenkontakt                                                                                                                                      • Engagement und Freude an Kommunikation                                                                                                                • Motivation, dich weiterzuentwickeln und zu lernen                                                                                                      • Spaß an Wirtschaftsfächern und Deutsch

Bewerbungsart: Ausschließlich online über [Jobs | Continental](https://jobs.continental.com/de/) (Papierbewerbungen und Bewerbungen per E-Mail finden keine Berücksichtigung)

Ansprechpartner: Ausbildungsabteilung, ausbildung@vergoelst.de (Nur bei Fragen zur Ausbildungsstelle zu benutzen, nicht für Bewerbungen)
"""

# Real posting: two separate requirements-shaped blocks - a short inline
# one ("Schulische Voraussetzung: ...") and a separate bulleted one
# ("Schlüsselqualifikationen") later in the same description.
HARTUNG_BAU_KAUFMANN = """**Ausbildung - Kaufmann/-frau für Büromanagement (m/w/d)**

**Ausbildungsdauer:** 3 Jahre

**Schulische Voraussetzung:** mindestens guter Realschulabschluss

**Schlüsselqualifikationen**

- Logisches Denken
- Mathematisches Verständnis
- Organisationstalent
- Kontaktfreudigkeit

**Karriere / Perspektiven**

- Baukaufmann
- Bilanzbuchhalter
"""


def test_stub_description_finds_no_requirements_section():
    section, found = extract_requirements_section(STUB_DESCRIPTION)
    assert found is False
    assert section == ""


def test_empty_description_finds_no_requirements_section():
    section, found = extract_requirements_section("")
    assert found is False
    assert section == ""
    section, found = extract_requirements_section(None)
    assert found is False


def test_curriculum_section_is_excluded_pfizer():
    section, found = extract_requirements_section(PFIZER_MECHATRONIKER)
    assert found is True
    assert "SPS-Programmierung" not in section
    assert "Vermittlung von mechanischen Kenntnissen" not in section


def test_requirements_section_is_included_pfizer():
    section, found = extract_requirements_section(PFIZER_MECHATRONIKER)
    assert "Sehr gute Deutschkenntnisse in Wort und Schrift" in section
    assert "Technisches Verständnis" in section


def test_benefits_section_is_excluded_pfizer():
    section, found = extract_requirements_section(PFIZER_MECHATRONIKER)
    assert "Praxiserfahrungen" not in section


def test_curriculum_section_is_excluded_sorg():
    section, found = extract_requirements_section(SORG_MECHATRONIKER)
    assert found is True
    assert "Programmieren mechatronischer Systeme" not in section
    assert "Grundlagen der Metallbearbeitung" not in section


def test_requirements_section_is_included_sorg():
    section, found = extract_requirements_section(SORG_MECHATRONIKER)
    assert "Farbsehtüchtigkeit" in section
    assert "Technisches Verständnis" in section


def test_contact_and_application_info_excluded_vergoelst():
    section, found = extract_requirements_section(VERGOELST_EINZELHANDEL)
    assert found is True
    assert "Bewerbungsart" not in section
    assert "ausbildung@vergoelst.de" not in section
    assert "continental.com" not in section


def test_school_subject_mention_still_present_in_isolated_text_vergoelst():
    # The isolator only narrows the *section* - it doesn't itself judge
    # school-subject vs. language-requirement wording, that's the AI
    # extractor's job (see test_job_requirements_extraction.py). Confirms
    # this section really does contain the trap for that layer to be
    # tested against.
    section, found = extract_requirements_section(VERGOELST_EINZELHANDEL)
    assert "Deutsch" in section


def test_multiple_requirements_blocks_both_captured_hartung_bau():
    section, found = extract_requirements_section(HARTUNG_BAU_KAUFMANN)
    assert found is True
    assert "Realschulabschluss" in section
    assert "Organisationstalent" in section
    assert "Kontaktfreudigkeit" in section


def test_career_prospects_section_excluded_hartung_bau():
    section, found = extract_requirements_section(HARTUNG_BAU_KAUFMANN)
    assert "Baukaufmann" not in section
    assert "Bilanzbuchhalter" not in section


def test_isolator_is_case_and_whitespace_tolerant():
    text = "some intro text\n\nWAS   DU   MITBRINGST:\n\n- Beispielskill\n\nDas erwartet dich:\n- unrelated"
    section, found = extract_requirements_section(text)
    assert found is True
    assert "Beispielskill" in section
    assert "unrelated" not in section
