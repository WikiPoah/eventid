from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import inspect

from app.database.db import db
from main import create_app


def test_session_cookie_security_defaults(monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})

    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] is False


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
                    "password": "password",
                    "confirm_password": "password",
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
