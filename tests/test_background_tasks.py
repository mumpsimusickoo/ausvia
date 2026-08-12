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
    assert "something went wrong" in task.error_message


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
