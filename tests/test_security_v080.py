import re

from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash

from app.database.db import db
from app.models.user import User
from main import create_app
from tests.conftest import login


def test_session_cookie_security_defaults(monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})

    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 12 * 60 * 60


def test_session_cookie_secure_can_be_enabled(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_login_rate_limit_has_helpful_response(client):
    for _attempt in range(3):
        response = client.post(
            "/login",
            data={"username": "missing", "password": "incorrect"},
        )
        assert response.status_code == 200

    response = client.post(
        "/login",
        data={"username": "missing", "password": "incorrect"},
    )
    assert response.status_code == 429
    assert b"Too many login attempts" in response.data
    assert "Retry-After" in response.headers


def test_login_get_requests_are_not_rate_limited(client):
    for _attempt in range(5):
        assert client.get("/login").status_code == 200


def test_failed_login_preserves_identifier_but_not_password(client):
    response = client.post(
        "/login",
        data={"identifier": "mistyped-user", "password": "secret-typo"},
    )

    assert b'value="mistyped-user"' in response.data
    assert b"Invalid username or password" in response.data
    assert b"secret-typo" not in response.data


def test_expired_login_form_recovers_with_fresh_token(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    login_page = client.get("/login")
    old_token = re.search(
        rb'name="csrf_token"\s+value="([^"]+)"', login_page.data
    ).group(1)
    with client.session_transaction() as browser_session:
        browser_session.pop("csrf_token", None)

    response = client.post(
        "/login?next=/manage-events",
        data={
            "csrf_token": old_token.decode(),
            "identifier": "wikipoah",
            "password": "never-preserve-this",
        },
    )

    assert response.status_code == 400
    assert b"Your form expired" in response.data
    assert b'value="wikipoah"' in response.data
    assert b"never-preserve-this" not in response.data
    assert b'name="csrf_token"' in response.data


def test_signup_checks_username_and_email_with_one_query(app, client):
    user_selects = 0

    def count_user_selects(_connection, _cursor, statement, *_args):
        nonlocal user_selects
        if statement.lstrip().upper().startswith("SELECT") and "users" in statement:
            user_selects += 1

    with app.app_context():
        sqlalchemy_event.listen(
            db.engine,
            "before_cursor_execute",
            count_user_selects,
        )
        try:
            response = client.post(
                "/signup",
                data={
                    "first_name": "Single",
                    "last_name": "Query",
                    "username": "singlequery",
                    "email": "single-query@example.test",
                    "password": "very-secure-42",
                    "confirm_password": "very-secure-42",
                },
            )
        finally:
            sqlalchemy_event.remove(
                db.engine,
                "before_cursor_execute",
                count_user_selects,
            )

    assert response.status_code == 302
    assert user_selects == 1


def test_signup_rejects_short_and_personal_passwords(client):
    base = {
        "first_name": "Secure",
        "last_name": "User",
        "username": "secureperson",
        "email": "secure@example.test",
    }

    short = client.post(
        "/signup",
        data={**base, "password": "short", "confirm_password": "short"},
    )
    personal_password = "secureperson-2026"
    personal = client.post(
        "/signup",
        data={
            **base,
            "password": personal_password,
            "confirm_password": personal_password,
        },
    )

    assert b"at least 12 characters" in short.data
    assert b"should not contain your username" in personal.data


def test_login_rotates_session_state_and_logout_clears_identity(app, client, users):
    with app.app_context():
        user = db.session.get(User, users[1])
        user.password_hash = generate_password_hash("safe-test-password")
        db.session.commit()

    with client.session_transaction() as browser_session:
        browser_session["untrusted_before_login"] = "remove-me"

    response = client.post(
        "/login",
        data={"identifier": "attendee", "password": "safe-test-password"},
    )
    assert response.status_code == 302
    with client.session_transaction() as browser_session:
        assert browser_session["user_id"] == users[1]
        assert browser_session["_permanent"] is True
        assert "untrusted_before_login" not in browser_session

    client.post("/logout")
    with client.session_transaction() as browser_session:
        assert "user_id" not in browser_session
        assert "untrusted_before_login" not in browser_session


def test_account_mutations_are_rate_limited(app, client, users, event_factory):
    app.config["ACCOUNT_ACTION_RATE_LIMIT"] = "2 per minute"
    event_id = event_factory()
    login(client, users[1])

    assert client.post(f"/events/{event_id}/favourite").status_code == 302
    assert client.post(f"/events/{event_id}/favourite").status_code == 302
    assert client.post(f"/events/{event_id}/favourite").status_code == 429


def test_event_query_indexes_exist(app):
    with app.app_context():
        index_names = {
            index["name"] for index in inspect(db.engine).get_indexes("events")
        }

    assert index_names == {
        "ix_events_organiser_start_datetime",
        "ix_events_privacy_city",
        "ix_events_privacy_start_datetime",
    }
