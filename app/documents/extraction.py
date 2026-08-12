"""
Document AI extraction (Phase 6, spec: "auto-classify/extract on upload,
always shown to the user for confirmation before being trusted"). This is
deliberately a plain keyword heuristic over the file's own extracted text,
not an LLM call - classifying "does this PDF contain the word Zeugnis"
doesn't need a language model, and keeping it heuristic means it's free,
instant, and 100% reproducible, consistent with the project's
deterministic-first principle. See AI.md for why this is the one
"extraction" feature with no AI-provider path at all, not even an optional
one.

PDF only - no OCR is available in this environment, so a scanned image or
a non-PDF upload simply gets no suggestion (honest, not a guess).
"""
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_CHARS_SCANNED = 4000
MAX_PAGES_SCANNED = 2

# Keywords are German-first (postings/documents in this product are
# overwhelmingly German-language application documents) with a few English
# equivalents. Order doesn't matter - every doc_type is scored independently.
DOC_TYPE_KEYWORDS = {
    "cv": ["lebenslauf", "curriculum vitae", "werdegang", "berufserfahrung"],
    "diploma": ["abschlusszeugnis", "zeugnis", "diplom", "abschluss"],
    "language_certificate": [
        "sprachzertifikat", "sprachniveau", "telc", "goethe-zertifikat",
        "sprachprüfung", "deutschtest", "cefr",
    ],
    "training_certificate": [
        "praktikumsbescheinigung", "ausbildungsnachweis", "teilnahmebescheinigung",
        "praktikumszeugnis",
    ],
    "recommendation_letter": ["empfehlungsschreiben", "arbeitszeugnis", "referenzschreiben"],
    "transcript": ["notenübersicht", "notenspiegel", "transcript of records"],
}


def _extract_text(file_path):
    try:
        reader = PdfReader(file_path)
        parts = [p.extract_text() or "" for p in reader.pages[:MAX_PAGES_SCANNED]]
        return "\n".join(parts)
    except (PdfReadError, OSError):
        return None


def suggest_doc_type(file_path, chosen_doc_type):
    """Returns a doc_type string if the file's own text suggests a
    *different* type than the user picked, else None. Never returns a
    suggestion that agrees with the user's choice - this only exists to
    flag a plausible mismatch worth a second look, not to praise a correct
    one."""
    text = _extract_text(file_path)
    if not text:
        return None

    text_lower = text[:MAX_CHARS_SCANNED].lower()
    scores = {
        doc_type: sum(1 for kw in keywords if kw in text_lower)
        for doc_type, keywords in DOC_TYPE_KEYWORDS.items()
    }
    scores = {k: v for k, v in scores.items() if v > 0}
    if not scores:
        return None

    best = max(scores, key=scores.get)
    return best if best != chosen_doc_type else None
