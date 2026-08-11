"""
German salutation logic (spec section 20): use the named contact only when
the source data already tells us how to address them (a stored "Frau"/"Herr"
prefix) - never guess gender from a first name. Falls back to the standard
formal neutral greeting otherwise.
"""
import re

FALLBACK = "Sehr geehrte Damen und Herren"


def build_salutation(contact_person):
    if not contact_person:
        return FALLBACK

    match = re.match(r"^\s*(Frau|Herr)\s+(.+)$", contact_person.strip())
    if match:
        title, name = match.groups()
        return f"Sehr geehrte{'r' if title == 'Herr' else ''} {title} {name.strip()}"

    return FALLBACK
