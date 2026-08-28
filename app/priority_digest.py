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

from flask_babel import gettext as _
from flask_babel import ngettext

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
    # i18n pass 2: parallel to `reasons` (same order/length) - a fixed,
    # never-translated vocabulary the template branches on for the digest
    # dot color (main/dashboard.html). Added because that branch used to
    # pattern-match substrings of the rendered *English* reason text
    # ("deadline" in reason.lower(), "Interview in" in reason, ...) - once
    # `reasons` became real translated UI copy, that match would silently
    # stop working the moment the UI renders in German. The reason text is
    # for reading; the code is for behavior - never derive one from the
    # other again.
    reason_codes: list = field(default_factory=list)


def _days_between(later, earlier):
    return (later - earlier).days


def application_digest_item(application, now):
    """Public since Screens pass 2 (Application Detail, 2026-08-27): reused
    directly by applications/routes.py's detail() route for the "Next step"
    rail card (one application, not the whole-user digest list below), not
    just internally by compute_priority_digest()."""
    job = application.job
    reasons = []
    reason_codes = []
    priority = 0

    if application.follow_up_date and application.follow_up_date <= now.date():
        reasons.append(_("Follow-up date has arrived"))
        reason_codes.append("follow_up_due")
        priority += 100
    if application.interview_date:
        days_until = _days_between(application.interview_date.date(), now.date())
        if 0 <= days_until <= UPCOMING_DAYS_THRESHOLD:
            reasons.append(ngettext("Interview in %(num)d day", "Interview in %(num)d days", days_until))
            reason_codes.append("interview_soon")
            priority += 90
    if job.application_deadline:
        days_until_deadline = _days_between(job.application_deadline, now.date())
        if 0 <= days_until_deadline <= UPCOMING_DAYS_THRESHOLD:
            reasons.append(
                ngettext(
                    "Application deadline in %(num)d day",
                    "Application deadline in %(num)d days",
                    days_until_deadline,
                )
            )
            reason_codes.append("deadline_soon")
            priority += 80
    if application.status == "ready":
        reasons.append(_("Approved but not yet sent"))
        reason_codes.append("approved_not_sent")
        priority += 50
    if application.status == "preparing" and not (application.cover_letter and application.email):
        reasons.append(_("Cover letter or email not finished yet"))
        reason_codes.append("prep_incomplete")
        priority += 30
    days_since_activity = _days_between(now.date(), application.updated_at.date())
    if days_since_activity >= STALLED_DAYS_THRESHOLD and application.status in ("sent", "follow_up"):
        reasons.append(ngettext("No activity for %(num)d day", "No activity for %(num)d days", days_since_activity))
        reason_codes.append("stalled")
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
        reason_codes=reason_codes,
    )


def _saved_job_digest_item(saved_job, match, now):
    job = saved_job.job
    reasons = []
    reason_codes = []
    priority = 0

    if match and match.score is not None and match.score >= 80:
        reasons.append(_("Strong match (%(score)d/100) - no application started yet", score=match.score))
        reason_codes.append("strong_match_unapplied")
        priority += 60
    if job.application_deadline:
        days_until_deadline = _days_between(job.application_deadline, now.date())
        if 0 <= days_until_deadline <= UPCOMING_DAYS_THRESHOLD:
            reasons.append(
                ngettext(
                    "Application deadline in %(num)d day",
                    "Application deadline in %(num)d days",
                    days_until_deadline,
                )
            )
            reason_codes.append("deadline_soon")
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
        reason_codes=reason_codes,
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
