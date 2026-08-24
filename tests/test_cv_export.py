"""Tests for the real profile-level CV PDF export (design-audit decision,
2026-08-24): deterministic rendering of stored profile data, no AI call,
independent of app.models.ai.CvProfileStatement - see
app/profile/cv_export.py's module docstring."""
import io

from pypdf import PdfReader

from app.models.profile import Education, Experience, Skill, Language
from app.profile.cv_export import build_cv_pdf, safe_cv_filename
from tests.conftest import login


def test_safe_cv_filename_sanitizes_and_handles_missing_name():
    assert safe_cv_filename("Lena Kovac") == "Lebenslauf_Lena_Kovac.pdf"
    assert safe_cv_filename(None) == "Lebenslauf_Kandidat.pdf"
    assert safe_cv_filename("") == "Lebenslauf_Kandidat.pdf"


def test_build_cv_pdf_renders_populated_profile(client, db, make_user):
    user = make_user(email="cv1@example.com", password="Password123!")
    profile = user.profile
    profile.first_name = "Lena"
    profile.last_name = "Kovac"
    profile.city = "Leipzig"
    profile.phone = "+49 176 0000000"
    db.session.add(Education(
        profile_id=profile.id, institution="Tehnicka skola", degree="Mittlere Reife", field="Elektrotechnik",
    ))
    db.session.add(Experience(
        profile_id=profile.id, company="Moeller und Sohn", role="Praktikum Elektromontage",
    ))
    db.session.add(Skill(profile_id=profile.id, name="SPS", proficiency="advanced"))
    db.session.add(Language(profile_id=profile.id, name="Deutsch", level="B2"))
    db.session.commit()

    pdf_bytes = build_cv_pdf(profile)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Lena Kovac" in text
    assert "Elektrotechnik" in text
    assert "Moeller" in text
    assert "SPS" in text
    assert "Deutsch" in text


def test_build_cv_pdf_omits_empty_sections_without_crashing(client, db, make_user):
    user = make_user(email="cv2@example.com", password="Password123!")
    pdf_bytes = build_cv_pdf(user.profile)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Education" not in text
    assert "Experience" not in text
    assert "Skills" not in text
    assert "Languages" not in text


def test_download_cv_route_returns_pdf(client, db, make_user):
    make_user(email="cv3@example.com", password="Password123!")
    login(client, "cv3@example.com", "Password123!")

    resp = client.get("/profile/cv.pdf")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert "Lebenslauf_" in resp.headers.get("Content-Disposition", "")


def test_cv_export_never_calls_an_ai_provider(client, db, make_user, monkeypatch):
    from app.ai import provider_factory

    def boom():
        raise AssertionError("CV export must not call an AI provider")

    monkeypatch.setattr(provider_factory, "get_provider", boom)

    make_user(email="cv4@example.com", password="Password123!")
    login(client, "cv4@example.com", "Password123!")

    resp = client.get("/profile/cv.pdf")
    assert resp.status_code == 200


def test_cv_export_does_not_touch_cv_profile_statement(client, db, make_user):
    from app.models.ai import CvProfileStatement

    make_user(email="cv5@example.com", password="Password123!")
    login(client, "cv5@example.com", "Password123!")

    client.get("/profile/cv.pdf")
    assert CvProfileStatement.query.count() == 0
