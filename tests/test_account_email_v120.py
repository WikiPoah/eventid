from datetime import UTC, datetime

from werkzeug.security import check_password_hash, generate_password_hash

from app.database.db import db
from app.models.user import User
from app.routes.auth import _account_token
from tests.conftest import login


def _user(app, *, verified=False):
    with app.app_context():
        user = User(
            first_name="Reset",
            last_name="Tester",
            username="resettester",
            email="reset@example.test",
            password_hash=generate_password_hash("Original-safe-phrase-92"),
            email_verified_at=datetime.now(UTC) if verified else None,
        )
        db.session.add(user)
        db.session.commit()
        return user.user_id


def test_forgot_password_is_private_and_sends_reset_link(app, client):
    user_id = _user(app)

    known = client.post(
        "/forgot-password", data={"email": "reset@example.test"}, follow_redirects=True
    )
    unknown = client.post(
        "/forgot-password", data={"email": "missing@example.test"}, follow_redirects=True
    )

    assert known.status_code == unknown.status_code == 200
    assert b"If an account uses that email" in known.data
    assert b"If an account uses that email" in unknown.data
    outbox = app.extensions["mail_outbox"]
    assert len(outbox) == 1
    assert outbox[0]["to"] == "reset@example.test"
    assert "/reset-password/" in outbox[0]["text"]
    assert user_id


def test_password_reset_is_single_use_and_invalidates_sessions(app, client):
    user_id = _user(app)
    with app.app_context():
        token = _account_token(db.session.get(User, user_id), "reset-password")

    response = client.post(
        f"/reset-password/{token}",
        data={
            "password": "Completely-new-safe-phrase-84",
            "confirm_password": "Completely-new-safe-phrase-84",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        user = db.session.get(User, user_id)
        assert check_password_hash(user.password_hash, "Completely-new-safe-phrase-84")
        assert user.auth_version == 1

    reused = client.get(f"/reset-password/{token}", follow_redirects=True)
    assert b"invalid or has expired" in reused.data


def test_email_verification_and_resend(app, client):
    user_id = _user(app)
    login(client, user_id)

    settings = client.get("/settings")
    assert b"Send Verification Email" in settings.data
    assert client.post("/resend-verification").status_code == 302
    message = app.extensions["mail_outbox"][0]
    token = message["text"].split("/verify-email/", 1)[1].split()[0]

    verified = client.get(f"/verify-email/{token}", follow_redirects=True)
    assert b"Your email address is verified" in verified.data
    with app.app_context():
        assert db.session.get(User, user_id).email_verified_at is not None

    settings = client.get("/settings")
    assert b"is verified" in settings.data
