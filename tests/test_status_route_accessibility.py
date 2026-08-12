"""Regression test for QA Phase 7 finding W4: the Wayfinding status markers'
'skipped' and 'future' (not-reached) states used to be visually identical
(same 14px size, same 2px ring weight, same white fill) and differed only
by ring color - a screen-reader-invisible, colorblind-invisible cue. Fixed
by giving 'skipped' a dashed ring instead of solid, a shape/pattern
difference that survives grayscale rendering."""
from tests.test_applications import make_job, start_application


def test_skipped_and_future_stations_render_with_different_ring_style(client, db, make_user):
    make_user(email="wayfind1@example.com", password="Password123!")
    login_resp = client.post(
        "/auth/login", data={"email": "wayfind1@example.com", "password": "Password123!"}, follow_redirects=True
    )
    assert login_resp.status_code == 200

    job = make_job(db)
    _, application = start_application(client, db, job)

    # Jump straight to "interview" - the application never explicitly passed
    # through "follow_up", so status_route.py marks that station skipped,
    # while "offer" (further down the route) remains genuinely not-reached.
    application.status = "interview"
    db.session.commit()

    resp = client.get(f"/applications/{application.id}")
    html = resp.get_data(as_text=True)

    assert "Skipped." in html or "the employer replied first" in html
    assert "Not reached yet." in html

    # the skipped station's marker must use a dashed ring...
    assert "border-2 border-dashed border-brand-600" in html
    # ...and the future station's marker must stay solid - proving the two
    # states are no longer visually identical apart from color.
    assert "border-2 border-solid border-ink/20" in html
