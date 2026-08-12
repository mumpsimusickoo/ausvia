"""Regression test for QA Phase 7 finding W1: registration used to check an
invitation code's use_count and then increment/save it as two separate
steps, so two concurrent requests against the same single-use code could
both pass the check before either saved - double-redeeming a code that
should only ever work once (most notably an 'admin' code minting two admin
accounts). Fixed with an atomic conditional UPDATE in app/auth/routes.py.

This can't use the shared `client`/`db` fixtures (bound to one process-local
`sqlite:///:memory:` connection - see the Phase 6 background-task lesson in
DECISIONS.md): a real concurrency test needs multiple independent database
connections genuinely racing, so each thread here gets its own Flask app
instance and its own connection to a shared temporary file-based database.
"""
import threading

from config import TestingConfig
from app import create_app
from app.extensions import db as _db
from app.models import InvitationCode, User


def _make_app(db_url):
    # TestingConfig.SQLALCHEMY_DATABASE_URI must be set *before* create_app()
    # runs, not after: create_app() now accesses db.engine directly (to
    # enable SQLite FK enforcement, see W2/app/__init__.py), which makes
    # Flask-SQLAlchemy build and cache the engine from whatever URI was in
    # the class at that moment - overriding app.config afterward is too late.
    TestingConfig.SQLALCHEMY_DATABASE_URI = db_url
    TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}
    return create_app("testing")


def test_concurrent_registration_cannot_double_redeem_a_single_use_code(tmp_path):
    original_uri = TestingConfig.SQLALCHEMY_DATABASE_URI
    original_engine_options = getattr(TestingConfig, "SQLALCHEMY_ENGINE_OPTIONS", None)
    db_url = f"sqlite:///{tmp_path / 'race.db'}"

    try:
        setup_app = _make_app(db_url)
        with setup_app.app_context():
            _db.create_all()
            _db.session.add(InvitationCode(code="RACE-TEST-0001", code_type="admin", max_uses=1))
            _db.session.commit()

        statuses = []
        lock = threading.Lock()

        def attempt(n):
            thread_app = _make_app(db_url)
            with thread_app.test_client() as client:
                resp = client.post(
                    "/auth/register",
                    data={
                        "access_code": "RACE-TEST-0001",
                        "email": f"racer{n}@example.com",
                        "password": "Password123!",
                        "confirm_password": "Password123!",
                    },
                    follow_redirects=True,
                )
            with lock:
                statuses.append(resp.status_code)

        threads = [threading.Thread(target=attempt, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # every request must get a normal response - concurrency must not
        # crash the route, only reject the losers with a clean error page
        assert all(s == 200 for s in statuses), statuses

        with setup_app.app_context():
            code = InvitationCode.query.filter_by(code="RACE-TEST-0001").first()
            assert code.use_count == 1, "a single-use code was redeemed more than once under concurrency"
            assert User.query.count() == 1, "more than one account was created from one single-use admin code"
            assert User.query.first().role == "admin"
    finally:
        TestingConfig.SQLALCHEMY_DATABASE_URI = original_uri
        if original_engine_options is None:
            if "SQLALCHEMY_ENGINE_OPTIONS" in TestingConfig.__dict__:
                delattr(TestingConfig, "SQLALCHEMY_ENGINE_OPTIONS")
        else:
            TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = original_engine_options
