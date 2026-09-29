from werkzeug.security import check_password_hash, generate_password_hash

from app.database.db import db
from app.models.user import User
from tests.conftest import login


def profile_data(**overrides):
    values = {
        "first_name": "Alice",
        "last_name": "Updated",
        "username": "alice_updated",
        "email": "alice-updated@example.test",
        "city": "Hamburg",
        "country": "Germany",
        "bio": "I enjoy community events.",
    }
    values.update(overrides)
    return values


def test_profile_requires_login(client):
    assert client.get("/profile").status_code == 302
    assert client.get("/settings").status_code == 302


def test_user_can_update_profile(app, client, users):
    login(client, users[1])

    response = client.post("/profile", data=profile_data(), follow_redirects=True)

    assert response.status_code == 200
    assert b"Profile updated successfully" in response.data
    assert b"Alice Updated" in response.data
    with app.app_context():
        user = db.session.get(User, users[1])
        assert user.username == "alice_updated"
        assert user.email == "alice-updated@example.test"
        assert user.city == "Hamburg"
        assert user.bio == "I enjoy community events."


def test_profile_rejects_duplicate_credentials(app, client, users):
    login(client, users[1])

    response = client.post(
        "/profile",
        data=profile_data(username="organiser"),
    )

    assert response.status_code == 200
    assert b"already in use" in response.data
    with app.app_context():
        assert db.session.get(User, users[1]).username == "attendee"


def test_username_and_email_can_only_change_once_per_week(app, client, users):
    login(client, users[1])
    first_change = client.post("/profile", data=profile_data(), follow_redirects=True)
    assert b"Profile updated successfully" in first_change.data

    second_change = client.post(
        "/profile",
        data=profile_data(
            username="alice_again",
            email="alice-again@example.test",
        ),
    )

    assert b"change your username again on" in second_change.data
    assert b"change your email again on" in second_change.data
    with app.app_context():
        user = db.session.get(User, users[1])
        assert user.username == "alice_updated"
        assert user.email == "alice-updated@example.test"


def test_non_identity_profile_details_have_no_weekly_cooldown(app, client, users):
    login(client, users[1])
    client.post("/profile", data=profile_data())

    response = client.post(
        "/profile",
        data=profile_data(city="Berlin", bio="A newly updated biography."),
        follow_redirects=True,
    )

    assert b"Profile updated successfully" in response.data
    with app.app_context():
        user = db.session.get(User, users[1])
        assert user.city == "Berlin"
        assert user.bio == "A newly updated biography."


def test_password_change_requires_current_password(app, client, users):
    with app.app_context():
        user = db.session.get(User, users[1])
        user.password_hash = generate_password_hash("old-safe-password")
        db.session.commit()
    login(client, users[1])

    response = client.post(
        "/settings",
        data={
            "current_password": "incorrect-password",
            "new_password": "brand-new-safe-42",
            "confirm_password": "brand-new-safe-42",
        },
    )

    assert b"current password is incorrect" in response.data


def test_password_change_invalidates_other_sessions(app, client, users):
    with app.app_context():
        user = db.session.get(User, users[1])
        user.password_hash = generate_password_hash("old-safe-password")
        db.session.commit()

    other_client = app.test_client()
    login(client, users[1])
    login(other_client, users[1])

    response = client.post(
        "/settings",
        data={
            "current_password": "old-safe-password",
            "new_password": "brand-new-safe-42",
            "confirm_password": "brand-new-safe-42",
        },
        follow_redirects=True,
    )

    assert b"Other signed-in sessions have been logged out" in response.data
    assert client.get("/settings").status_code == 200
    assert other_client.get("/my-events").status_code == 302
    with app.app_context():
        user = db.session.get(User, users[1])
        assert user.auth_version == 1
        assert check_password_hash(user.password_hash, "brand-new-safe-42")


def test_account_menu_links_to_profile_and_settings(client, users):
    login(client, users[1])

    response = client.get("/")

    assert b'href="/profile"' in response.data
    assert b'href="/settings"' in response.data
    assert b"My Profile" in response.data
