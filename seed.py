"""
Local development bootstrap: creates the first admin account (if none exists)
and a couple of invitation codes so the access-code flow can be exercised
end-to-end. Run via `flask seed`. Prints credentials to the console only -
never writes them to the database logs.
"""
import secrets

from app.extensions import db
from app.models import User, InvitationCode, CandidateProfile
from app.models.access_code import generate_code


def run_seed():
    if User.query.filter_by(role="admin").first():
        print("An admin user already exists - skipping admin creation.")
    else:
        admin_email = "admin@example.com"
        admin_password = secrets.token_urlsafe(12)

        admin = User(email=admin_email, role="admin", plan="premium", email_verified=True)
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.flush()
        db.session.add(CandidateProfile(user_id=admin.id, contact_email=admin_email))

        print("Created admin account:")
        print(f"  email:    {admin_email}")
        print(f"  password: {admin_password}")
        print("  (change this password after first login)")

    for code_type, max_uses in [("admin", 1), ("trial", 5)]:
        code_value = generate_code()
        while InvitationCode.query.filter_by(code=code_value).first():
            code_value = generate_code()
        code = InvitationCode(code=code_value, code_type=code_type, max_uses=max_uses, notes="Seeded for local dev")
        db.session.add(code)
        print(f"Created {code_type} invitation code: {code_value} (max uses: {max_uses})")

    db.session.commit()
