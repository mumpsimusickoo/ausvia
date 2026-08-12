"""
Minimal background-task runner (Phase 6 - see ROADMAP.md's "background job
system" item). No broker, no separate worker process: an in-process
ThreadPoolExecutor plus a BackgroundTask DB row per task, so a route can
return immediately instead of blocking the request on a slow network call
(Gmail API today; PDF assembly and AI generation are natural next
candidates, not yet retrofitted - see DECISIONS.md for why this pass
scoped itself to one call site rather than all of them at once).

This matches the project's established "no new infra beyond SQLite"
pattern (no Docker/Redis available in this dev environment). A real
deployment needing durability across restarts or multi-process scaling
would swap this module for Celery/RQ + Redis without changing the
BackgroundTask row shape or the submit_task() call sites - that's the
point of keeping the row shape broker-agnostic.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

from app.extensions import db
from app.models.task import BackgroundTask
from app.models.user import utcnow

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ausvia-task")

# Phase 7 remediation (QA finding W3): BackgroundTask.error_message used to
# store the raw exception text, which could contain server-internal details
# (a filesystem path, a library's repr of its own state, ...) and was shown
# to the end user verbatim. The real exception still goes to the server log
# via logger.exception() below - only a safe, task-appropriate message ever
# reaches error_message / the template that renders it.
_SAFE_ERROR_MESSAGES = {
    "gmail_check_replies": "Couldn't check for replies right now. Please try again in a moment.",
}
_DEFAULT_SAFE_ERROR_MESSAGE = "This background task couldn't complete. Please try again in a moment."


def submit_task(user, task_type, target_fn, *args, context=None, **kwargs):
    """Records a BackgroundTask row (status=pending) and runs
    target_fn(*args, **kwargs) on a worker thread with its own Flask app
    context - target_fn must not rely on the *request* context (it will
    have ended by the time the thread runs), only on plain arguments passed
    in explicitly. Returns the BackgroundTask immediately so the caller's
    route can redirect right away.

    Under TESTING, runs target_fn synchronously instead of on a thread -
    the same "eager" pattern Celery's task_always_eager uses, for two
    concrete reasons rather than convenience alone: (1) the test suite's
    SQLite database is in-memory, and a genuinely separate thread opening
    its own connection would see an empty database, not the test's data;
    (2) synchronous execution means tests assert on real outcomes
    immediately, no polling/sleeping for a thread that may not have
    finished yet. Tests exercise the real target_fn either way - only the
    threading is swapped out, not the logic."""
    task = BackgroundTask(user_id=user.id, task_type=task_type, status="pending", context=context)
    db.session.add(task)
    db.session.commit()

    if current_app.config.get("TESTING"):
        _run_task(task.id, target_fn, args, kwargs)
    else:
        app = current_app._get_current_object()
        _executor.submit(_run_in_app_context, app, task.id, target_fn, args, kwargs)
    return task


def _run_in_app_context(app, task_id, target_fn, args, kwargs):
    with app.app_context():
        _run_task(task_id, target_fn, args, kwargs)


def _run_task(task_id, target_fn, args, kwargs):
    task = db.session.get(BackgroundTask, task_id)
    task.status = "running"
    task.started_at = utcnow()
    db.session.commit()
    try:
        result = target_fn(*args, **kwargs)
        task.status = "done"
        task.result_message = (str(result)[:500] if result else "Completed.")
    except Exception:
        # Full exception + traceback goes to the server log only - never to
        # the user-facing error_message field (see _SAFE_ERROR_MESSAGES above).
        logger.exception("Background task %s (%s) failed", task_id, task.task_type)
        task.status = "error"
        task.error_message = _SAFE_ERROR_MESSAGES.get(task.task_type, _DEFAULT_SAFE_ERROR_MESSAGE)
    finally:
        task.finished_at = utcnow()
        db.session.commit()
