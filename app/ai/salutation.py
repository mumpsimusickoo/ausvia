"""
German salutation logic (spec section 20): use the named contact only when
the source data already tells us how to address them (a stored "Frau"/"Herr"
prefix) - never guess gender from a first name. Falls back to the standard
formal neutral greeting when no name is known at all.

Contact-info follow-up pass (2026-08-30): a real name WITHOUT a title is a
common, correctly-extracted result, not a rarity - the extraction prompts
(app/ai/prompts/job_requirements_extraction.py,
app/ai/prompts/manual_import_extraction.py) both deliberately instruct
"never add a title the text doesn't state", so any posting that names a
contact without the German Herr/Frau convention (increasingly common in
informal, du-form postings - real examples seen live this session: ALDI
Nord, CASISOFT) correctly produces a title-less contact_person. Before this
fix, that fell all the way through to FALLBACK - a fully generic greeting
even though a real name was sitting right there - because a title-less
name matched neither the "Frau"/"Herr" branch nor anything else. Guessing
"Frau" or "Herr" from the name to force it into that branch was
considered and rejected: that's the exact fabrication risk the "never add
a title the text doesn't state" extraction rule already protects against,
just approached from the other direction, and unreliable for non-German or
ambiguous names. Instead: a title-less name gets a genuine, standard,
gender-neutral formal German opener - "Guten Tag [Name]" - real
personalization without fabricating anything the source never stated.
"""
import re

FALLBACK = "Sehr geehrte Damen und Herren"


def build_salutation(contact_person):
    if not contact_person:
        return FALLBACK

    contact_person = contact_person.strip()
    if not contact_person:
        return FALLBACK

    match = re.match(r"^(Frau|Herr)\s+(.+)$", contact_person)
    if match:
        title, name = match.groups()
        return f"Sehr geehrte{'r' if title == 'Herr' else ''} {title} {name.strip()}"

    return f"Guten Tag {contact_person}"
