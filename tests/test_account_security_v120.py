from werkzeug.security import generate_password_hash

from app.database.db import db
from app.models.security import SecurityEvent, UserSession
from app.models.user import User


def _account(app):
    with app.app_context():
        user = User(
            first_name="Secure",
            last_name="Tester",
            username="securetester",
            email="secure@example.test",
            password_hash=generate_password_hash("Original-secure-phrase-72"),
        )
        db.session.add(user)
        db.session.commit()
        return user.user_id


def _login(client):
    return client.post(
        "/login",
        data={
            "identifier": "securetester",
            "password": "Original-secure-phrase-72",
        },
    )


def test_login_tracks_hashed_session_and_security_activity(app, client):
    user_id = _account(app)
    assert _login(client).status_code == 302

    with client.session_transaction() as browser_session:
        raw_token = browser_session["session_token"]
    with app.app_context():
        tracked = db.session.query(UserSession).filter_by(user_id=user_id).one()
        event = db.session.query(SecurityEvent).filter_by(user_id=user_id).one()
        assert tracked.token_hash != raw_token
        assert len(tracked.token_hash) == 64
        assert event.event_type == "login"


def test_logout_other_devices_is_enforced_on_their_next_request(app):
    _account(app)
    first = app.test_client()
    second = app.test_client()
    assert _login(first).status_code == 302
    assert _login(second).status_code == 302

    settings = first.get("/settings")
    assert settings.data.count(b"Log Out") >= 2
    response = first.post("/settings/sessions/revoke-others", follow_redirects=True)
    assert b"Logged out 1 other session" in response.data

    rejected = second.get("/settings")
    assert rejected.status_code == 302
    assert "/login" in rejected.headers["Location"]


def test_password_change_alerts_and_replaces_current_session(app, client):
    user_id = _account(app)
    _login(client)
    response = client.post(
        "/settings",
        data={
            "current_password": "Original-secure-phrase-72",
            "new_password": "Replacement-violet-phrase-93",
            "confirm_password": "Replacement-violet-phrase-93",
        },
    )
    assert response.status_code == 302
    assert app.extensions["mail_outbox"][-1]["subject"] == (
        "Your eventid password changed"
    )
    with app.app_context():
        active = db.session.query(UserSession).filter_by(
            user_id=user_id, revoked_at=None
        )
        assert active.count() == 1
        assert (
            db.session.query(SecurityEvent)
            .filter_by(user_id=user_id, event_type="password_changed")
            .count()
            == 1
        )
