from datetime import date, datetime, timedelta

from app import priority_digest
from app.models import Application, Job, SavedJob
from app.models.ai import JobMatch
from app.models.user import utcnow
from tests.conftest import login


def make_job(db, **overrides):
    kwargs = dict(dedup_key="digest-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_empty_digest_is_honest_not_padded(client, db, make_user):
    make_user(email="dig1@example.com", password="Password123!")
    login(client, "dig1@example.com", "Password123!")

    resp = client.get("/digest")
    assert resp.status_code == 200
    assert b"Nothing needs attention right now" in resp.data


def test_follow_up_date_due_surfaces_with_high_priority(app, db, make_user):
    user = make_user(email="dig2@example.com")
    job = make_job(db, dedup_key="digest-followup")
    application = Application(
        user_id=user.id, job_id=job.id, status="follow_up",
        follow_up_date=date.today() - timedelta(days=1),
    )
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert len(items) == 1
    assert items[0].kind == "application"
    assert "Follow-up date has arrived" in items[0].reasons[0]


def test_upcoming_interview_surfaces(app, db, make_user):
    user = make_user(email="dig3@example.com")
    job = make_job(db, dedup_key="digest-interview")
    application = Application(
        user_id=user.id, job_id=job.id, status="interview",
        interview_date=datetime.combine(date.today() + timedelta(days=3), datetime.min.time()),
    )
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert len(items) == 1
    assert "Interview in 3 days" in items[0].reasons


def test_distant_interview_does_not_surface(app, db, make_user):
    user = make_user(email="dig4@example.com")
    job = make_job(db, dedup_key="digest-distant-interview")
    application = Application(
        user_id=user.id, job_id=job.id, status="interview",
        interview_date=datetime.combine(date.today() + timedelta(days=30), datetime.min.time()),
    )
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert items == []


def test_approaching_application_deadline_surfaces(app, db, make_user):
    user = make_user(email="dig5@example.com")
    job = make_job(db, dedup_key="digest-deadline", application_deadline=date.today() + timedelta(days=5))
    application = Application(user_id=user.id, job_id=job.id, status="preparing")
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert any("deadline in 5 days" in r for r in items[0].reasons)


def test_ready_but_not_sent_surfaces(app, db, make_user):
    user = make_user(email="dig6@example.com")
    job = make_job(db, dedup_key="digest-ready")
    application = Application(user_id=user.id, job_id=job.id, status="ready")
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert "Approved but not yet sent" in items[0].reasons


def test_stalled_sent_application_surfaces(app, db, make_user):
    user = make_user(email="dig7@example.com")
    job = make_job(db, dedup_key="digest-stalled")
    old_date = utcnow() - timedelta(days=20)
    application = Application(user_id=user.id, job_id=job.id, status="sent", updated_at=old_date)
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert any("No activity for 20 days" in r for r in items[0].reasons)


def test_recently_sent_application_does_not_surface_as_stalled(app, db, make_user):
    user = make_user(email="dig8@example.com")
    job = make_job(db, dedup_key="digest-fresh")
    application = Application(user_id=user.id, job_id=job.id, status="sent")
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert items == []


def test_terminal_status_applications_excluded(app, db, make_user):
    user = make_user(email="dig9@example.com")
    job = make_job(db, dedup_key="digest-terminal", application_deadline=date.today() + timedelta(days=1))
    application = Application(user_id=user.id, job_id=job.id, status="rejected")
    db.session.add(application)
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert items == []


def test_saved_job_with_strong_match_surfaces(app, db, make_user):
    user = make_user(email="dig10@example.com")
    job = make_job(db, dedup_key="digest-saved-match")
    db.session.add(SavedJob(user_id=user.id, job_id=job.id))
    db.session.add(JobMatch(user_id=user.id, job_id=job.id, score=85))
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert len(items) == 1
    assert items[0].kind == "saved_job"
    assert "Strong match (85/100)" in items[0].reasons[0]


def test_saved_job_with_weak_match_does_not_surface(app, db, make_user):
    user = make_user(email="dig11@example.com")
    job = make_job(db, dedup_key="digest-saved-weak")
    db.session.add(SavedJob(user_id=user.id, job_id=job.id))
    db.session.add(JobMatch(user_id=user.id, job_id=job.id, score=40))
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert items == []


def test_saved_job_already_applied_is_not_double_counted(app, db, make_user):
    user = make_user(email="dig12@example.com")
    job = make_job(db, dedup_key="digest-both", application_deadline=date.today() + timedelta(days=2))
    db.session.add(SavedJob(user_id=user.id, job_id=job.id))
    db.session.add(JobMatch(user_id=user.id, job_id=job.id, score=95))
    db.session.add(Application(user_id=user.id, job_id=job.id, status="preparing"))
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    # only the application-side item, not a second saved-job entry for the same job
    assert len(items) == 1
    assert items[0].kind == "application"


def test_items_sorted_by_priority_descending(app, db, make_user):
    user = make_user(email="dig13@example.com")
    job1 = make_job(db, dedup_key="digest-low", title="Low priority job")
    job2 = make_job(db, dedup_key="digest-high", title="High priority job")
    db.session.add(Application(user_id=user.id, job_id=job1.id, status="ready"))
    db.session.add(Application(
        user_id=user.id, job_id=job2.id, status="follow_up",
        follow_up_date=date.today() - timedelta(days=1),
    ))
    db.session.commit()

    items = priority_digest.compute_priority_digest(user)
    assert len(items) == 2
    assert items[0].title == "High priority job"  # follow-up-due outranks ready-not-sent


def test_digest_is_per_user(app, db, make_user):
    user1 = make_user(email="dig14a@example.com")
    user2 = make_user(email="dig14b@example.com")
    job = make_job(db, dedup_key="digest-peruser")
    db.session.add(Application(user_id=user1.id, job_id=job.id, status="ready"))
    db.session.commit()

    assert len(priority_digest.compute_priority_digest(user1)) == 1
    assert len(priority_digest.compute_priority_digest(user2)) == 0


def test_digest_link_shown_on_dashboard(client, db, make_user):
    make_user(email="dig15@example.com", password="Password123!")
    login(client, "dig15@example.com", "Password123!")

    resp = client.get("/dashboard")
    assert b"Show my priority digest" in resp.data
