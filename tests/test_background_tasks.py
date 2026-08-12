from app.models.task import BackgroundTask
from app.tasks.runner import submit_task


def test_submit_task_runs_synchronously_under_testing_and_records_success(app, db, make_user):
    user = make_user(email="bt1@example.com")

    def _work(x, y):
        return f"sum is {x + y}"

    task = submit_task(user, "test_task", _work, 2, 3)

    # under TESTING, submit_task runs eagerly (see runner.py docstring) - no
    # sleep/poll needed, the outcome is already committed.
    db.session.refresh(task)
    assert task.status == "done"
    assert task.result_message == "sum is 5"
    assert task.started_at is not None
    assert task.finished_at is not None


def test_submit_task_records_error_without_raising_to_caller(app, db, make_user):
    user = make_user(email="bt2@example.com")

    def _fails():
        raise ValueError("something went wrong")

    task = submit_task(user, "test_task", _fails)

    db.session.refresh(task)
    assert task.status == "error"
    assert task.error_message is not None


def test_submit_task_error_message_is_safe_not_the_raw_exception(app, db, make_user):
    """Regression test for QA Phase 7 finding W3: BackgroundTask.error_message
    used to store str(exception) verbatim and the application template
    rendered it directly to the user - a background Gmail-check failure once
    showed a real server filesystem path. The raw exception must never reach
    this field; only a safe, generic (or task-specific) message may."""
    user = make_user(email="bt5@example.com")

    def _fails_with_sensitive_detail():
        raise FileNotFoundError(
            r"[Errno 2] No such file or directory: 'C:\Users\itash\OneDrive\Desktop\ausbildung-finder\credentials.json'"
        )

    task = submit_task(user, "gmail_check_replies", _fails_with_sensitive_detail)

    db.session.refresh(task)
    assert task.status == "error"
    assert "credentials.json" not in task.error_message
    assert "Users" not in task.error_message
    assert "Errno" not in task.error_message
    assert task.error_message == "Couldn't check for replies right now. Please try again in a moment."


def test_submit_task_unknown_task_type_gets_generic_safe_message(app, db, make_user):
    user = make_user(email="bt6@example.com")

    def _fails():
        raise RuntimeError("some internal detail nobody outside should see")

    task = submit_task(user, "some_future_task_type", _fails)

    db.session.refresh(task)
    assert task.status == "error"
    assert "internal detail" not in task.error_message
    assert task.error_message == "This background task couldn't complete. Please try again in a moment."


def test_submit_task_stores_context(app, db, make_user):
    user = make_user(email="bt3@example.com")

    task = submit_task(user, "test_task", lambda: None, context={"application_id": 42})

    assert task.context == {"application_id": 42}
    assert db.session.get(BackgroundTask, task.id).context == {"application_id": 42}


def test_background_task_is_active_property(app, db, make_user):
    user = make_user(email="bt4@example.com")
    task = BackgroundTask(user_id=user.id, task_type="test_task", status="pending")
    db.session.add(task)
    db.session.commit()
    assert task.is_active is True

    task.status = "running"
    assert task.is_active is True

    task.status = "done"
    assert task.is_active is False

    task.status = "error"
    assert task.is_active is False
