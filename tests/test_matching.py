from app.ai.matching import compute_match
from app.models import Education, Skill, Language, Preference, Job

BASE_JOB_KWARGS = dict(dedup_key="test-key", employment_type="Ausbildung")


def make_job(db, **overrides):
    kwargs = dict(BASE_JOB_KWARGS)
    kwargs.update(overrides)
    job = Job(title=kwargs.pop("title", "Elektroniker"), **kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_no_profile_returns_insufficient_data(app, db):
    job = make_job(db, skills=["PLC"])
    result = compute_match(None, job)
    assert result.score is None
    assert result.recommendation == "insufficient_data"


def test_trivial_location_only_match_scores_100(app, db, make_user):
    user = make_user(email="m1@example.com")
    profile = user.profile
    job = make_job(db)  # no skills/language/education/start_date -> only location evaluable

    result = compute_match(profile, job)
    assert result.score == 100
    assert "Open to opportunities Germany-wide" in result.strengths
    assert set(result.skipped_categories) == {"skills", "language", "education", "start_date"}


def test_strong_match_scenario(app, db, make_user):
    user = make_user(email="m2@example.com")
    profile = user.profile
    db.session.add(Skill(profile_id=profile.id, name="PLC"))
    db.session.add(Language(profile_id=profile.id, name="German", level="B2"))
    db.session.add(Education(profile_id=profile.id, institution="TU Berlin", degree="Elektrotechnik"))
    db.session.add(Preference(profile_id=profile.id, locations=["Berlin"], desired_start_date="2027", open_to_relocation=True))
    db.session.commit()

    job = make_job(
        db,
        title="Elektroniker für Automatisierungstechnik",
        skills=["PLC", "STEP7"],
        language_requirements=[{"language": "German", "level": "B1"}],
        education_requirements="Elektrotechnik oder vergleichbar",
        location="Berlin",
        start_date="2027-09-01",
    )

    result = compute_match(profile, job)
    assert result.score is not None and result.score >= 70
    assert "PLC" in result.strengths
    assert any(g.label == "STEP7" and g.status == "preferred_missing" for g in result.gaps)
    assert any("German B2" in s for s in result.strengths)
    assert result.recommendation in ("strong_candidate", "possible_candidate")


def test_language_level_below_requirement_is_a_gap_not_a_match(app, db, make_user):
    user = make_user(email="m3@example.com")
    profile = user.profile
    db.session.add(Language(profile_id=profile.id, name="German", level="A2"))
    db.session.commit()

    job = make_job(db, language_requirements=[{"language": "German", "level": "B2"}])
    result = compute_match(profile, job)

    # "Open to opportunities Germany-wide" (location) legitimately contains "German" -
    # check specifically that no *language* strength was recorded, not a bare substring.
    assert not any(s.startswith("German ") for s in result.strengths)
    gap = next(g for g in result.gaps if "German" in g.label)
    assert gap.status == "preferred_missing"
    assert "A2" in gap.note


def test_missing_required_language_entirely(app, db, make_user):
    user = make_user(email="m4@example.com")
    profile = user.profile
    db.session.commit()

    job = make_job(db, language_requirements=[{"language": "German", "level": "B1"}])
    result = compute_match(profile, job)

    gap = next(g for g in result.gaps if "German" in g.label)
    assert gap.status == "required_missing"


def test_location_mismatch_not_open_to_relocation_is_required_gap(app, db, make_user):
    user = make_user(email="m5@example.com")
    profile = user.profile
    db.session.add(Preference(profile_id=profile.id, locations=["Hamburg"], open_to_relocation=False))
    db.session.commit()

    job = make_job(db, location="München")
    result = compute_match(profile, job)

    gap = next(g for g in result.gaps if g.label == "Location")
    assert gap.status == "required_missing"


def test_weak_match_scenario_gets_low_score_and_weak_recommendation(app, db, make_user):
    user = make_user(email="m6@example.com")
    profile = user.profile
    db.session.add(Language(profile_id=profile.id, name="German", level="A1"))
    db.session.add(Preference(profile_id=profile.id, locations=["Hamburg"], open_to_relocation=False))
    db.session.commit()

    job = make_job(
        db,
        skills=["PLC", "STEP7", "TIA Portal"],
        language_requirements=[{"language": "German", "level": "C1"}],
        location="München",
    )
    result = compute_match(profile, job)

    assert result.score is not None and result.score < 40
    assert result.recommendation == "weak_match"
