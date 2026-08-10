from app.models.profile import Education, Skill, Language
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
