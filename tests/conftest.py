import shutil
import tempfile

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User, InvitationCode, CandidateProfile
from app.models.access_code import generate_code


@pytest.fixture
def upload_dir():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def app(upload_dir):
    application = create_app("testing")
    application.config["UPLOAD_DIR"] = upload_dir
    application.config["GENERATED_DIR"] = upload_dir

    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def trial_code(db):
    code = InvitationCode(code=generate_code(), code_type="trial", max_uses=2)
    db.session.add(code)
    db.session.commit()
    return code


@pytest.fixture
def admin_code(db):
    code = InvitationCode(code=generate_code(), code_type="admin", max_uses=1)
    db.session.add(code)
    db.session.commit()
    return code


@pytest.fixture
def make_user(db):
    def _make(email="user@example.com", password="Password123!", role="user"):
        user = User(email=email, role=role, plan="trial")
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        db.session.add(CandidateProfile(user_id=user.id, contact_email=email))
        db.session.commit()
        return user

    return _make


def login(client, email, password):
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)
