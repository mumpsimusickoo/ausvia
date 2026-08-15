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
# as an explicit list mainly for documentation/readability.
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


def extract_requirements_section(description):
    """Returns (section_text, found: bool). found=False means no
    confident requirements section was located - the caller should fall
    back to the full description rather than treat this as an error."""
    if not description:
        return "", False

    lines = description.splitlines()
    n = len(lines)
    sections = []
    i = 0
    while i < n:
        stripped_line = lines[i].strip()
        normalized_full = _normalize(stripped_line)
        matched = normalized_full and any(
            normalized_full.startswith(phrase) for phrase in REQUIREMENTS_HEADERS
        )
        if not matched:
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
            if normalized and _looks_like_a_heading(lines[j], normalized):
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
