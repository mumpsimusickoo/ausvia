import io
import os
import tempfile

from app.documents.extraction import suggest_doc_type
from pdfmerge import text_to_pdf_bytes


def _write_pdf(text):
    """Real, parseable PDF with actual text content - a hand-crafted
    magic-byte-only fixture would pass upload validation but isn't
    representative here, same lesson as the Phase 4 corrupt-PDF bug."""
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(text_to_pdf_bytes(text))
    return path


def test_suggest_doc_type_detects_cv_keywords():
    path = _write_pdf("LEBENSLAUF\n\nBerufserfahrung:\n2022-2023 Praktikum bei Elektro Hoffmann GmbH")
    try:
        assert suggest_doc_type(path, chosen_doc_type="other") == "cv"
    finally:
        os.remove(path)


def test_suggest_doc_type_detects_diploma_keywords():
    path = _write_pdf("ABSCHLUSSZEUGNIS\n\nBerufskolleg Essen-West\nFachhochschulreife")
    try:
        assert suggest_doc_type(path, chosen_doc_type="cv") == "diploma"
    finally:
        os.remove(path)


def test_suggest_doc_type_returns_none_when_it_agrees_with_choice():
    path = _write_pdf("LEBENSLAUF\n\nBerufserfahrung: ...")
    try:
        # already chosen "cv", and the text also suggests "cv" - nothing to flag
        assert suggest_doc_type(path, chosen_doc_type="cv") is None
    finally:
        os.remove(path)


def test_suggest_doc_type_returns_none_for_unrecognized_text():
    path = _write_pdf("Some generic text with no matching keywords at all.")
    try:
        assert suggest_doc_type(path, chosen_doc_type="other") is None
    finally:
        os.remove(path)


def test_suggest_doc_type_returns_none_for_unreadable_file():
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4\nnot a real pdf structure")
    try:
        assert suggest_doc_type(path, chosen_doc_type="other") is None
    finally:
        os.remove(path)
