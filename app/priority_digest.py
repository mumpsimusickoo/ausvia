"""On-demand priority digest (Phase 9, Wave 2) - which saved jobs and active
applications deserve attention this week, computed purely from existing
deterministic signals (match score, application status, time since last
activity, known deadlines). No AI call, no invented signals - the same
"compute the real thing in plain Python first" pattern as
app/ai/matching.py:compute_match(). Deliberately request-triggered, not
scheduled: this app has no scheduler (see app/tasks/runner.py's own
docstring), and building one is out of scope for this pass - see the
Phase 9 report for the scheduling-delivery-mechanism options this implies,
none of which are implemented here.
"""
from dataclasses import dataclass, field

from app.models.job import SavedJob
from app.models.application import Application, APPLICATION_STATUSES
from app.models.ai import JobMatch
from app.models.user import utcnow

# Active = still in flight - excludes states where there's nothing left to do
TERMINAL_STATUSES = ("accepted", "rejected", "withdrawn", "expired")
ACTIVE_STATUSES = tuple(s for s in APPLICATION_STATUSES if s not in TERMINAL_STATUSES)

STALLED_DAYS_THRESHOLD = 14
UPCOMING_DAYS_THRESHOLD = 7


@dataclass
class DigestItem:
    kind: str  # "application" | "saved_job"
    title: str
    company_name: str | None
    url_kwargs: dict
    priority: int  # higher = more urgent, purely for sort order - never shown as a fake score
    reasons: list = field(default_factory=list)


def _days_between(later, earlier):
    return (later - earlier).days


def application_digest_item(application, now):
    """Public since Screens pass 2 (Application Detail, 2026-08-27): reused
    directly by applications/routes.py's detail() route for the "Next step"
    rail card (one application, not the whole-user digest list below), not
    just internally by compute_priority_digest()."""
    job = application.job
    reasons = []
    priority = 0

    if application.follow_up_date and application.follow_up_date <= now.date():
        reasons.append("Follow-up date has arrived")
        priority += 100
    if application.interview_date:
        days_until = _days_between(application.interview_date.date(), now.date())
        if 0 <= days_until <= UPCOMING_DAYS_THRESHOLD:
            reasons.append(f"Interview in {days_until} day{'s' if days_until != 1 else ''}")
            priority += 90
    if job.application_deadline:
        days_until_deadline = _days_between(job.application_deadline, now.date())
        if 0 <= days_until_deadline <= UPCOMING_DAYS_THRESHOLD:
            reasons.append(f"Application deadline in {days_until_deadline} day{'s' if days_until_deadline != 1 else ''}")
            priority += 80
    if application.status == "ready":
        reasons.append("Approved but not yet sent")
        priority += 50
    if application.status == "preparing" and not (application.cover_letter and application.email):
        reasons.append("Cover letter or email not finished yet")
        priority += 30
    days_since_activity = _days_between(now.date(), application.updated_at.date())
    if days_since_activity >= STALLED_DAYS_THRESHOLD and application.status in ("sent", "follow_up"):
        reasons.append(f"No activity for {days_since_activity} days")
        priority += 40

    if not reasons:
        return None

    return DigestItem(
        kind="application",
        title=job.title,
        company_name=job.company_name,
        url_kwargs={"application_id": application.id},
        priority=priority,
        reasons=reasons,
    )


def _saved_job_digest_item(saved_job, match, now):
    job = saved_job.job
    reasons = []
    priority = 0

    if match and match.score is not None and match.score >= 80:
        reasons.append(f"Strong match ({match.score}/100) - no application started yet")
        priority += 60
    if job.application_deadline:
        days_until_deadline = _days_between(job.application_deadline, now.date())
        if 0 <= days_until_deadline <= UPCOMING_DAYS_THRESHOLD:
            reasons.append(f"Application deadline in {days_until_deadline} day{'s' if days_until_deadline != 1 else ''}")
            priority += 70

    if not reasons:
        return None

    return DigestItem(
        kind="saved_job",
        title=job.title,
        company_name=job.company_name,
        url_kwargs={"job_id": job.id},
        priority=priority,
        reasons=reasons,
    )


def compute_priority_digest(user):
    """Returns a list of DigestItem, most urgent first. Only includes items
    with at least one real reason to surface - an application/saved job
    with nothing time-sensitive or stalled about it simply isn't in the
    list, rather than being shown with a hollow "no action needed" entry."""
    now = utcnow()

    applications = (
        Application.query.filter_by(user_id=user.id)
        .filter(Application.status.in_(ACTIVE_STATUSES))
        .all()
    )
    items = []
    for application in applications:
        item = application_digest_item(application, now)
        if item:
            items.append(item)

    applied_job_ids = {a.job_id for a in applications}
    saved_jobs = SavedJob.query.filter_by(user_id=user.id).all()
    for saved_job in saved_jobs:
        if saved_job.job_id in applied_job_ids:
            continue  # already covered as an application above
        match = JobMatch.query.filter_by(user_id=user.id, job_id=saved_job.job_id).first()
        item = _saved_job_digest_item(saved_job, match, now)
        if item:
            items.append(item)

    items.sort(key=lambda i: i.priority, reverse=True)
    return items
