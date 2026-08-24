"""On-demand "Jetzt prüfen" job radar (design-audit decision, 2026-08-24):
searches the currently-enabled job sources for the user's stated preferred
fields and reports which jobs turned out to be genuinely new. Deliberately
request-triggered only - no scheduler, no cron, no background polling. That
automatic version was explicitly deferred; see app/tasks/runner.py's and
app/priority_digest.py's docstrings for the standing no-scheduler
architecture this stays inside of.

Reuses ingest_search() exactly as app/jobs/routes.py's search() view does -
same adapters, same enable/disable settings, same ProviderQueryCache
cooldown protecting metered APIs from repeat "Check now" clicks. The only
difference is the query terms come from Preference.fields instead of a
typed search box, and this captures which Job rows were newly created
(ingest_search's own IngestResult only carries counts, not identities) so
they can be listed back to the user on the dashboard.
"""
from app.extensions import db
from app.jobs.ingest import ingest_search
from app.jobs.matching import get_or_compute_match
from app.models.job import Job, JobRadarStatus
from app.models.user import utcnow

# Bounds how many external searches one "Check now" click can trigger - a
# profile listing many desired fields still only costs a few adapter calls,
# not one per field. Only the first (primary) desired location is searched;
# a full fields x locations cross-product would multiply calls well beyond
# what a single on-demand click should cost.
MAX_FIELDS_PER_CHECK = 3
MAX_STORED_HITS = 20


def run_job_radar(user):
    """Runs one on-demand check for `user` and returns (new_jobs, errors):
    new_jobs is a list of newly-discovered Job rows sorted by match score
    (best first), errors is IngestResult.errors accumulated across the
    searches performed. Raises ValueError if the user hasn't set any
    desired fields yet - there is nothing to search for without that."""
    profile = user.profile
    preference = profile.preference if profile else None
    fields = (preference.fields if preference else None) or []
    if not fields:
        raise ValueError(
            "Set at least one desired field in your Ausbildung preferences before checking for new listings."
        )

    locations = (preference.locations if preference else None) or []
    location = locations[0] if locations else None

    start = utcnow()
    errors = []
    for field in fields[:MAX_FIELDS_PER_CHECK]:
        outcome = ingest_search(field, location=location)
        errors.extend(outcome.errors)

    new_jobs = Job.query.filter(Job.discovered_at >= start).order_by(Job.discovered_at.desc()).all()
    matches = {job.id: get_or_compute_match(user, job) for job in new_jobs}
    new_jobs.sort(key=lambda j: matches[j.id].score or 0, reverse=True)

    status = JobRadarStatus.query.filter_by(user_id=user.id).first()
    if status is None:
        status = JobRadarStatus(user_id=user.id)
        db.session.add(status)
    status.checked_at = utcnow()
    status.new_job_count = len(new_jobs)
    status.new_job_ids = [job.id for job in new_jobs[:MAX_STORED_HITS]]
    db.session.commit()

    return new_jobs, errors
