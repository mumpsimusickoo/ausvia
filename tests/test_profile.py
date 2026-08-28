from datetime import date

from app.models.document import Document
from app.models.profile import Education, Skill, Language
from app.profile.routes import _age, _completeness_lines, _language_proof_note
from tests.conftest import login


def test_update_personal_info(client, db, make_user):
    make_user(email="p1@example.com", password="Password123!")
    login(client, "p1@example.com", "Password123!")

    resp = client.post(
        "/profile/personal",
        data={"first_name": "Ilias", "last_name": "Jabbour", "city": "Berlin", "country": "Germany"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Personal information updated" in resp.data
    assert b"Ilias" in resp.data


def test_add_and_delete_education(client, db, make_user):
    make_user(email="p2@example.com", password="Password123!")
    login(client, "p2@example.com", "Password123!")

    resp = client.post(
        "/profile/education/add",
        data={"institution": "TU Berlin", "degree": "Bachelor", "field": "Electronics"},
        follow_redirects=True,
    )
    assert b"TU Berlin" in resp.data
    entry = Education.query.filter_by(institution="TU Berlin").first()
    assert entry is not None

    resp = client.post(f"/profile/education/{entry.id}/delete", follow_redirects=True)
    assert b"TU Berlin" not in resp.data


def test_cannot_delete_another_users_education_entry(client, db, make_user):
    owner = make_user(email="owner@example.com", password="Password123!")
    intruder = make_user(email="intruder@example.com", password="Password123!")

    entry = Education(profile_id=owner.profile.id, institution="Secret University")
    db.session.add(entry)
    db.session.commit()

    login(client, "intruder@example.com", "Password123!")
    resp = client.post(f"/profile/education/{entry.id}/delete")
    assert resp.status_code == 404

    remaining = db.session.get(Education, entry.id)
    assert remaining is not None  # was not deleted


def test_add_skill_and_language(client, db, make_user):
    make_user(email="p3@example.com", password="Password123!")
    login(client, "p3@example.com", "Password123!")

    resp = client.post("/profile/skill/add", data={"name": "PLC", "proficiency": "advanced"}, follow_redirects=True)
    assert b"PLC" in resp.data
    assert Skill.query.filter_by(name="PLC").first() is not None

    resp = client.post("/profile/language/add", data={"name": "German", "level": "B1"}, follow_redirects=True)
    assert b"German" in resp.data
    assert Language.query.filter_by(name="German").first() is not None


def test_update_preferences(client, db, make_user):
    make_user(email="p4@example.com", password="Password123!")
    login(client, "p4@example.com", "Password123!")

    resp = client.post(
        "/profile/preferences",
        data={
            "fields": "automation, electronics",
            "locations": "NRW, Bayern",
            "desired_start_date": "2027",
            "min_german_level": "B1",
            "max_distance_km": "100",
            "open_to_relocation": "y",
            "other_notes": "",
        },
        follow_redirects=True,
    )
    assert b"Preferences updated" in resp.data

    from app.models import User

    user = User.query.filter_by(email="p4@example.com").first()
    assert user.profile.preference.fields == ["automation", "electronics"]
    assert user.profile.preference.locations == ["NRW", "Bayern"]


def test_profile_view_requires_login(client):
    resp = client.get("/profile/", follow_redirects=True)
    assert b"Log in" in resp.data


def test_completeness_checklist_matches_percent(client, db, make_user):
    # Screens pass 3 (Dashboard, 2026-08-27): completeness_checklist() backs
    # completeness_percent() - same eight checks, same weighting, only the
    # per-item labels are new (needed so the dashboard can name what's
    # missing instead of a bare percentage).
    user = make_user(email="p5@example.com", password="Password123!")
    profile = user.profile

    # make_user() pre-fills contact_email from the account email, so that's
    # the one check already satisfied on a fresh profile.
    checklist = profile.completeness_checklist()
    assert len(checklist) == 8
    satisfied = {label for label, ok in checklist if ok}
    assert satisfied == {"Contact email"}
    assert profile.completeness_percent() == round(100 * 1 / 8)

    profile.first_name = "Ilias"
    profile.last_name = "Jabbour"
    db.session.commit()

    checklist = profile.completeness_checklist()
    satisfied = {label for label, ok in checklist if ok}
    assert satisfied == {"Contact email", "Name"}
    assert profile.completeness_percent() == round(100 * 2 / 8)


def test_completeness_lines_pairs_done_and_missing_phrasing(client, db, make_user):
    # Screens pass 5 (Profile, 2026-08-28): the Profile screen's checklist
    # reuses completeness_checklist()'s data (not a second calculation),
    # paired with real done/missing sentences for its own list UI.
    user = make_user(email="p6@example.com", password="Password123!")
    lines = _completeness_lines(user.profile.completeness_checklist())
    assert len(lines) == 8
    by_text = {text: ok for text, ok in lines}
    assert by_text["Contact email provided"] is True
    assert by_text["Name missing"] is False


def test_completeness_checklist_shown_on_profile_page(client, db, make_user):
    make_user(email="p7@example.com", password="Password123!")
    login(client, "p7@example.com", "Password123!")

    resp = client.get("/profile/")
    assert b"Contact email provided" in resp.data
    assert b"Name missing" in resp.data


def test_grounding_statement_shown_on_profile_page(client, db, make_user):
    make_user(email="p8@example.com", password="Password123!")
    login(client, "p8@example.com", "Password123!")

    resp = client.get("/profile/")
    assert b"nothing is ever invented to fill" in resp.data


def test_age_computed_from_date_of_birth():
    today = date.today()
    # Exactly 20 years ago today - just turned 20.
    assert _age(date(today.year - 20, today.month, today.day)) == 20
    # Born the same month/day but 20 years ago plus one day - the birthday
    # falls tomorrow, so still 19, not the naive year-subtraction's 20.
    from datetime import timedelta
    tomorrow = today + timedelta(days=1)
    assert _age(date(tomorrow.year - 20, tomorrow.month, tomorrow.day)) == 19
    assert _age(None) is None


def test_language_proof_note_native_language():
    class FakeLang:
        level = "Native"
        name = "Croatian"

    assert _language_proof_note(FakeLang(), has_german_certificate=True) == "Native language"


def test_language_proof_note_german_with_and_without_certificate():
    class FakeGerman:
        level = "B2"
        name = "German"

    assert _language_proof_note(FakeGerman(), has_german_certificate=True) == "Certificate on file"
    assert _language_proof_note(FakeGerman(), has_german_certificate=False) == "School-level, no certificate on file"


def test_language_proof_note_non_german_stays_honest_about_missing_data():
    # No is_primary_english_cert (or equivalent) exists anywhere in the
    # schema - the schema simply can't answer "does a certificate exist
    # for English", so this must not claim it can (see DECISIONS.md).
    class FakeEnglish:
        level = "B1"
        name = "English"

    assert _language_proof_note(FakeEnglish(), has_german_certificate=False) is None


def test_language_proof_note_reflects_real_uploaded_certificate(client, db, make_user):
    user = make_user(email="p9@example.com", password="Password123!")
    login(client, "p9@example.com", "Password123!")
    profile = user.profile
    profile.languages.append(Language(name="German", level="B2"))
    db.session.commit()

    resp = client.get("/profile/")
    assert b"School-level, no certificate on file" in resp.data

    db.session.add(Document(
        user_id=user.id, doc_type="language_certificate", original_filename="cert.pdf",
        stored_filename="cert-stored.pdf", storage_path="x/cert-stored.pdf",
        mime_type="application/pdf", file_size=1000, is_primary_german_cert=True,
    ))
    db.session.commit()

    resp = client.get("/profile/")
    assert b"Certificate on file" in resp.data
    assert b"School-level, no certificate on file" not in resp.data
