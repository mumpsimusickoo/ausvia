"""
Deterministic isolation of a German Ausbildung posting's requirements/
profile section from its full free-text description (job-description
extraction pass). Pure text heuristics, no AI - app/ai/job_requirements_
extraction.py uses this to narrow what the AI is shown, so it never even
sees curriculum/duties/marketing text when a clear requirements section
exists, rather than relying on the prompt alone to ignore it.

Header lists come from the explicit list given for this task, extended
with headers actually observed in real live-fetched Arbeitsagentur
descriptions during the investigation this was built from (Stadt
Arnsberg, Bundesnetzagentur, Hartung Bau, Pfizer, SORG-Gruppe, Vergölst).
Deliberately NOT treated as exhaustive: any line that merely *looks* like
a section heading (markdown heading marks, fully bold, or a short line
ending in ":"/"?") is also treated as a section boundary even if it
matches neither list below - the goal is "find the segment that clearly
starts a requirements section and ends at the next section of any kind",
not "match one of these exact phrases and nothing else".

A posting can have more than one requirements-shaped section (e.g. a
short "Schulische Voraussetzung:" line followed later by a separate
"Schlüsselqualifikationen" block) - confirmed in real data - so this
scans the whole description and concatenates every matching section,
rather than stopping at the first one.

extract_contact_section() (contact/email extraction pass) reuses the same
scanning engine (_scan_sections()) with its own header list and its own,
deliberately looser boundary rule - see that function's docstring for why
a second, independent isolator exists rather than extending the
requirements one: contact/application info structurally lives in a
different part of a posting and needs different matching, not because
the underlying algorithm needed to change.
"""
import re

REQUIREMENTS_HEADERS = [
    "das bringst du mit",
    "das bringen sie mit",
    "was du mitbringst",
    "was sie mitbringen",
    "voraussetzungen",
    "dein profil",
    "ihr profil",
    "was wir erwarten",
    "was erwarten wir von dir",
    "wir erwarten von dir",
    "was solltest du mitbringen",
    "deine qualifikationen",
    "anforderungsprofil",
    "schlüsselqualifikationen",
    "schulische voraussetzung",
]

# Used only to recognize where a requirements section ENDS (treated as a
# section boundary like any other heading) - never themselves a source of
# extraction input. Not load-bearing on their own - the generic
# "_looks_like_a_heading" check below already catches most of these; kept
# as an explicit list mainly for documentation/readability. Also reused
# by extract_contact_section() as one of its topic-boundary signals (see
# _is_topic_boundary below).
NON_REQUIREMENTS_HEADERS = [
    "das erwartet dich",
    "was dich erwartet",
    "kernpunkte der ausbildung",
    "ausbildungsinhalte",
    "deine aufgaben",
    "tätigkeiten während der ausbildung",
    "was wir dir bieten",
    "das bieten wir dir",
    "deine stärken",
    "deine perspektive",
    "dein weg zu uns",
]

# Contact/application-info section headers (contact-info extraction pass).
# Deliberately looser matching than REQUIREMENTS_HEADERS' plain startswith
# list - see _matches_contact_header below - since real postings phrase
# this heading far more variably ("Interessiert?", "Postalische
# Bewerbungen an:", "Digitale Bewerbungen...", "Ansprechpartner:").
#
# Deliberately NOT a bare "kontakt" stem: "kontaktfreudigkeit" (a generic
# soft trait, already excluded from skills in the extraction prompt for
# the same reason) is a real, common word in these postings and starts
# with that exact prefix - found live via a false-positive test failure
# against a real fixture. "kontaktperson"/"kontaktdaten" etc. are specific
# enough not to collide with it the same way.
CONTACT_HEADER_STEMS = [
    "interessiert",
    "interesse geweckt",
    "kontaktperson",
    "kontaktdaten",
    "kontaktinformation",
    "kontaktmöglichkeit",
    "kontaktangaben",
    "ansprechpartner",
    "ansprechpartnerin",
    "jetzt bewerben",
    "so bewirbst du dich",
    "wir freuen uns auf",
]


def _normalize(line):
    text = line.strip()
    text = re.sub(r"^#+\s*", "", text)  # markdown heading marks
    text = re.sub(r"\*+", "", text)  # bold/italic markers
    text = re.sub(r"[^\w\säöüÄÖÜß?]", " ", text)  # strip emoji/punctuation, keep umlauts and "?"
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _looks_like_a_heading(raw_line, normalized):
    """Generic heading detector, independent of either phrase list above -
    this is what makes the isolator tolerant of headings that were never
    explicitly enumerated, per the "do not assume these are exhaustive"
    requirement."""
    if not normalized:
        return False
    stripped = raw_line.strip()

    # "Label: rest of line" pattern (e.g. "Bewerbungsart: ausschließlich
    # online über [Jobs | Continental](...long url...)", "Ansprechpartner:
    # ..."). Checked before the overall-length gate below, on purpose -
    # found live: Vergölst's "Bewerbungsart:" line is long overall (a long
    # URL follows the colon) but its *label* is short, and without this
    # check running independently of line length, application/contact-info
    # lines right after a real requirements section (no blank line or
    # standalone heading in between) got swept into the extracted section.
    if ":" in stripped:
        label = stripped.split(":", 1)[0].strip()
        if label and len(label) <= 40 and len(label.split()) <= 4:
            return True

    if len(normalized) > 60:
        return False
    if stripped.startswith("#"):
        return True
    if stripped.startswith("**"):
        return True
    if stripped.endswith(":") or stripped.endswith("?"):
        return True
    return False


def _matches_requirements_header(raw_line, normalized):
    return bool(normalized) and any(normalized.startswith(phrase) for phrase in REQUIREMENTS_HEADERS)


def _matches_contact_header(raw_line, normalized):
    """Opens a contact/application section on either an explicit stem
    match, or - since real postings phrase this so variably ("Postalische
    Bewerbungen an:", "Digitale Bewerbungen entweder unter:") - any
    heading-shaped line that simply mentions "bewerbung". The
    heading-shape requirement (short/colon-ending/bold/# line, via the
    same _looks_like_a_heading already proven for the requirements
    isolator) is what keeps this from firing on a random sentence deep in
    running prose that happens to mention the word."""
    if not normalized:
        return False
    if any(normalized.startswith(stem) for stem in CONTACT_HEADER_STEMS):
        return True
    return "bewerbung" in normalized and _looks_like_a_heading(raw_line, normalized)


def _is_topic_boundary(raw_line, normalized):
    """Where a CONTACT section ends. Deliberately narrower than
    _looks_like_a_heading (which the requirements isolator uses to end a
    section): a real application/contact block legitimately contains its
    own short sub-lines ("oder an:", "unter:") that must stay *inside*
    the collected section, not be mistaken for a new topic. Only a real,
    substantive topic heading (a requirements header, or a known
    non-requirements one) ends a contact section - not any short label."""
    return (
        any(normalized.startswith(phrase) for phrase in REQUIREMENTS_HEADERS)
        or any(normalized.startswith(phrase) for phrase in NON_REQUIREMENTS_HEADERS)
    )


def _scan_sections(description, is_section_start, is_section_boundary):
    """Shared engine behind extract_requirements_section() and
    extract_contact_section(): scans line-by-line for is_section_start()
    matches, then collects everything up to the next is_section_boundary()
    match (or end of description) as that section's text - concatenating
    every matching section found, not just the first."""
    if not description:
        return "", False

    lines = description.splitlines()
    n = len(lines)
    sections = []
    i = 0
    while i < n:
        stripped_line = lines[i].strip()
        normalized_full = _normalize(stripped_line)
        if not is_section_start(stripped_line, normalized_full):
            i += 1
            continue

        collected = []
        # Some real headers carry the requirement inline on the same line
        # (e.g. "**Schulische Voraussetzung:** mindestens guter
        # Realschulabschluss") rather than only in the lines below it.
        if ":" in stripped_line:
            after_colon = stripped_line.split(":", 1)[1]
            after_colon = re.sub(r"\*+", "", after_colon).strip()
            if after_colon:
                collected.append(after_colon)

        j = i + 1
        while j < n:
            normalized = _normalize(lines[j])
            if normalized and is_section_boundary(lines[j], normalized):
                break
            collected.append(lines[j])
            j += 1

        section_text = "\n".join(l for l in collected if l.strip()).strip()
        if section_text:
            sections.append(section_text)
        i = j

    if not sections:
        return "", False
    return "\n\n".join(sections), True


def extract_requirements_section(description):
    """Returns (section_text, found: bool). found=False means no
    confident requirements section was located - the caller should fall
    back to the full description rather than treat this as an error."""
    return _scan_sections(description, _matches_requirements_header, _looks_like_a_heading)


def extract_contact_section(description):
    """Returns (section_text, found: bool) - same shape as
    extract_requirements_section(). Isolates a posting's application/
    contact-instructions section (e.g. "Interessiert?", "Postalische
    Bewerbungen an:", "Ansprechpartner:") so app/ai/job_requirements_
    extraction.py's contact-person/contact-email extraction can be
    grounded against just that text, without ever showing the AI the
    full description (which could contain curriculum/marketing text) the
    same way the requirements isolator already avoids that for skills.

    A separate isolator rather than reusing extract_requirements_section()
    with a merged header list: contact/application headers are phrased far
    more variably in practice, and - critically - contact blocks routinely
    contain their own short "Label:" sub-lines ("oder an:", "unter:") as
    *continuation* content, which the requirements isolator's boundary
    rule (any short "Label:" line ends the section) would incorrectly cut
    off before reaching the actual email. See _is_topic_boundary above.

    Known v1 limitation, same character as the requirements isolator's own
    (documented there): a posting that states contact info as a single
    dense run-on sentence with no heading at all (observed live, e.g. a
    SORG-Gruppe posting: "Bitte sende deine Bewerbung per E-Mail an:
    CAREER@SORG.DE") won't be found - found=False, safe under-extraction,
    not a fabrication risk."""
    return _scan_sections(description, _matches_contact_header, _is_topic_boundary)
