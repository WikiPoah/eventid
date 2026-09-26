from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from app.database.db import db
from app.models.attendance import Attendance
from app.models.event import Event
from app.models.favourite import Favourite
from app.models.user import User
from tests.conftest import login


def attendance_count(app, event_id):
    with app.app_context():
        return Attendance.query.filter_by(event_id=event_id).count()


def test_authenticated_user_can_attend_public_event(app, client, users, event_factory):
    event_id = event_factory()
    login(client, users[1])
    response = client.post(f"/events/{event_id}/attend", follow_redirects=True)
    assert response.status_code == 200
    assert b"You are now attending this event." in response.data
    assert attendance_count(app, event_id) == 1


def test_duplicate_attendance_is_prevented(app, client, users, event_factory):
    event_id = event_factory()
    login(client, users[1])
    client.post(f"/events/{event_id}/attend")
    response = client.post(f"/events/{event_id}/attend", follow_redirects=True)
    assert b"already attending" in response.data
    assert attendance_count(app, event_id) == 1


def test_organiser_cannot_attend_own_event(app, client, users, event_factory):
    event_id = event_factory()
    login(client, users[0])
    response = client.post(f"/events/{event_id}/attend", follow_redirects=True)
    assert b"Organisers cannot register" in response.data
    assert attendance_count(app, event_id) == 0


def test_unauthorized_user_cannot_attend_private_event(
    app, client, users, event_factory
):
    event_id = event_factory(privacy="Private")
    login(client, users[1])
    response = client.post(f"/events/{event_id}/attend")
    assert response.status_code == 403
    assert attendance_count(app, event_id) == 0


def test_unauthorized_user_cannot_view_private_event(client, users, event_factory):
    event_id = event_factory(privacy="Private")
    login(client, users[1])
    assert client.get(f"/events/{event_id}").status_code == 403


def test_user_can_leave_and_repeated_leave_is_safe(app, client, users, event_factory):
    event_id = event_factory()
    login(client, users[1])
    client.post(f"/events/{event_id}/attend")
    response = client.post(f"/events/{event_id}/leave", follow_redirects=True)
    assert b"no longer attending" in response.data
    response = client.post(f"/events/{event_id}/leave", follow_redirects=True)
    assert b"not registered" in response.data
    assert attendance_count(app, event_id) == 0


def test_unlimited_event_accepts_attendees(app, users, event_factory):
    event_id = event_factory(capacity=None)
    for user_id in users[1:]:
        client = app.test_client()
        login(client, user_id)
        assert client.post(f"/events/{event_id}/attend").status_code == 302
    assert attendance_count(app, event_id) == 2


def test_full_event_rejects_attendance_and_displays_count(app, users, event_factory):
    event_id = event_factory(capacity=1)
    first_client = app.test_client()
    login(first_client, users[1])
    first_client.post(f"/events/{event_id}/attend")

    second_client = app.test_client()
    login(second_client, users[2])
    response = second_client.post(f"/events/{event_id}/attend", follow_redirects=True)
    assert b"This event is full." in response.data
    assert b"1 of 1 places have been taken." in response.data
    assert attendance_count(app, event_id) == 1


def test_capacity_below_existing_count_remains_closed(app, users, event_factory):
    event_id = event_factory(capacity=1)
    with app.app_context():
        db.session.add_all(
            [
                Attendance(user_id=users[1], event_id=event_id),
                Attendance(user_id=users[2], event_id=event_id),
            ]
        )
        db.session.commit()
        event = db.session.get(Event, event_id)
        event.capacity = 1
        db.session.commit()

        extra = User(
            first_name="Extra",
            last_name="User",
            username="extra",
            email="extra@example.test",
            password_hash="unused",
        )
        db.session.add(extra)
        db.session.commit()
        extra_id = extra.user_id

    client = app.test_client()
    login(client, extra_id)
    client.post(f"/events/{event_id}/attend")
    assert attendance_count(app, event_id) == 2


def test_my_events_only_shows_current_users_attendance(
    app, client, users, event_factory
):
    mine = event_factory(title="My Registration")
    theirs = event_factory(title="Someone Else Registration")
    with app.app_context():
        db.session.add_all(
            [
                Attendance(user_id=users[1], event_id=mine),
                Attendance(user_id=users[2], event_id=theirs),
            ]
        )
        db.session.commit()
    login(client, users[1])
    response = client.get("/my-events")
    assert b"My Registration" in response.data
    assert b"Someone Else Registration" not in response.data


def test_user_can_favourite_event_and_see_it_in_my_events(
    app, client, users, event_factory
):
    event_id = event_factory(title="Saved Favourite")
    login(client, users[1])

    response = client.post(
        f"/events/{event_id}/favourite",
        data={"next": "/events"},
        follow_redirects=True,
    )

    assert b"added to your favourites" in response.data
    assert b"Saved Favourite" in client.get("/my-events").data
    with app.app_context():
        assert db.session.get(Favourite, (users[1], event_id)) is not None


def test_favourite_heart_toggles_event_off(app, client, users, event_factory):
    event_id = event_factory(title="Toggle Favourite")
    login(client, users[1])
    client.post(f"/events/{event_id}/favourite", data={"next": "/events"})

    response = client.post(
        f"/events/{event_id}/favourite",
        data={"next": "/my-events"},
        follow_redirects=True,
    )

    assert b"removed from your favourites" in response.data
    with app.app_context():
        assert db.session.get(Favourite, (users[1], event_id)) is None


def test_favourite_can_toggle_without_page_reload(app, client, users, event_factory):
    event_id = event_factory(title="Async Favourite")
    login(client, users[1])

    response = client.post(
        f"/events/{event_id}/favourite",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.json == {
        "event_id": event_id,
        "is_favourite": True,
        "message": "Event added to your favourites.",
    }


def test_my_events_favourites_use_carousel_and_link_to_complete_page(
    app, client, users, event_factory
):
    event_ids = [event_factory(title=f"Saved Event {number}") for number in range(5)]
    with app.app_context():
        db.session.add_all(
            Favourite(user_id=users[1], event_id=event_id) for event_id in event_ids
        )
        db.session.commit()

    login(client, users[1])
    my_events_response = client.get("/my-events")
    favourites_response = client.get("/favourites")

    assert b'id="my-favourites-viewport"' in my_events_response.data
    assert b"data-carousel-next" in my_events_response.data
    assert b"See all favourites" in my_events_response.data
    for number in range(5):
        assert f"Saved Event {number}".encode() in favourites_response.data


def test_private_event_cannot_be_favourited(app, client, users, event_factory):
    event_id = event_factory(privacy="Private")
    login(client, users[1])

    assert client.post(f"/events/{event_id}/favourite").status_code == 403
    with app.app_context():
        assert Favourite.query.count() == 0


def test_old_attending_events_url_redirects_to_my_events(client, users):
    login(client, users[1])
    response = client.get("/my-attending-events")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/my-events")


def test_attendee_names_are_only_shown_to_organiser(app, users, event_factory):
    event_id = event_factory()

    with app.app_context():
        db.session.add(
            Attendance(
                user_id=users[1],
                event_id=event_id,
            )
        )
        db.session.commit()

    attendee_client = app.test_client()
    login(attendee_client, users[1])
    response = attendee_client.get(f"/events/{event_id}")

    assert b"Attendance Requests" not in response.data

    organiser_client = app.test_client()
    login(organiser_client, users[0])
    response = organiser_client.get(f"/events/{event_id}")

    assert b"Attendance Requests" in response.data


def test_public_registration_deadline_closes_attendance(
    app, client, users, event_factory
):
    event_id = event_factory(
        registration_deadline=datetime.now() - timedelta(minutes=1)
    )
    login(client, users[1])

    response = client.post(f"/events/{event_id}/attend", follow_redirects=True)

    assert b"Registration for this event has closed" in response.data
    assert attendance_count(app, event_id) == 0


def test_private_invite_requires_allowed_email_and_organiser_approval(
    app, users, event_factory
):
    event_id = event_factory(
        privacy="Private",
        invite_token="private-test-token",
        invite_expires_at=datetime.now() + timedelta(days=2),
        invited_emails="attendee@example.test",
    )

    attendee_client = app.test_client()
    login(attendee_client, users[1])
    invite_response = attendee_client.get(
        f"/events/{event_id}?invite=private-test-token"
    )
    assert invite_response.status_code == 302
    assert invite_response.headers["Location"].endswith(f"/events/{event_id}")
    invite_response = attendee_client.get(invite_response.headers["Location"])
    assert invite_response.status_code == 200

    request_response = attendee_client.post(
        f"/events/{event_id}/attend", follow_redirects=True
    )
    assert b"pending organiser approval" in request_response.data
    with app.app_context():
        attendance = db.session.get(Attendance, (users[1], event_id))
        assert attendance.status == "Pending"

    organiser_client = app.test_client()
    login(organiser_client, users[0])
    approval_response = organiser_client.post(
        f"/events/{event_id}/requests/{users[1]}/approve",
        follow_redirects=True,
    )
    assert b"request approved" in approval_response.data
    with app.app_context():
        attendance = db.session.get(Attendance, (users[1], event_id))
        assert attendance.status == "Going"


def test_private_invite_rejects_expired_link_and_unlisted_email(
    app, users, event_factory
):
    expired_id = event_factory(
        privacy="Private",
        invite_token="expired-token",
        invite_expires_at=datetime.now() - timedelta(minutes=1),
    )
    restricted_id = event_factory(
        privacy="Private",
        invite_token="restricted-token",
        invite_expires_at=datetime.now() + timedelta(days=1),
        invited_emails="someone-else@example.test",
    )
    client = app.test_client()
    login(client, users[1])

    assert client.get(f"/events/{expired_id}?invite=expired-token").status_code == 403
    assert (
        client.get(f"/events/{restricted_id}?invite=restricted-token").status_code
        == 403
    )


def test_organiser_can_revoke_and_restore_private_access(app, users, event_factory):
    event_id = event_factory(
        privacy="Private",
        invite_token="revocation-token",
        invite_expires_at=datetime.now() + timedelta(days=1),
        invited_emails="attendee@example.test",
    )
    with app.app_context():
        db.session.add(Attendance(user_id=users[1], event_id=event_id, status="Going"))
        db.session.commit()

    organiser = app.test_client()
    login(organiser, users[0])
    revoked = organiser.post(
        f"/events/{event_id}/attendees/{users[1]}/revoke",
        follow_redirects=True,
    )
    assert b"Access revoked" in revoked.data

    attendee = app.test_client()
    login(attendee, users[1])
    assert attendee.get(f"/events/{event_id}").status_code == 403
    assert (
        attendee.get(f"/events/{event_id}?invite=revocation-token").status_code == 403
    )

    restored = organiser.post(
        f"/events/{event_id}/attendees/{users[1]}/restore",
        follow_redirects=True,
    )
    assert b"Access restored as a pending request" in restored.data
    assert attendee.get(f"/events/{event_id}").status_code == 200
    with app.app_context():
        attendance = db.session.get(Attendance, (users[1], event_id))
        assert attendance.status == "Pending"


def test_private_attendance_actions_return_in_place_updates(
    app, client, users, event_factory
):
    event_id = event_factory(privacy="Private", capacity=3)
    with app.app_context():
        db.session.add_all(
            [
                Attendance(user_id=users[1], event_id=event_id, status="Pending"),
                Attendance(user_id=users[2], event_id=event_id, status="Going"),
            ]
        )
        db.session.commit()
    login(client, users[0])

    response = client.post(
        f"/events/{event_id}/requests/{users[1]}/approve",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    result = response.get_json()
    assert result["status"] == "Going"
    assert result["status_label"] == "Approved"
    assert result["counts"]["Pending"] == 0
    assert result["counts"]["Going"] == 2
    assert result["actions"][0]["label"] == "Revoke Access"

    response = client.post(
        f"/events/{event_id}/attendees/{users[1]}/revoke",
        headers={"Accept": "application/json"},
    )
    result = response.get_json()
    assert response.status_code == 200
    assert result["status"] == "Revoked"
    assert result["actions"][0]["label"] == "Restore as Pending"


def test_private_access_controls_require_organiser_and_private_event(
    app, client, users, event_factory
):
    private_id = event_factory(privacy="Private")
    public_id = event_factory()
    with app.app_context():
        db.session.add_all(
            [
                Attendance(user_id=users[1], event_id=private_id, status="Going"),
                Attendance(user_id=users[1], event_id=public_id, status="Going"),
            ]
        )
        db.session.commit()

    login(client, users[2])
    assert (
        client.post(f"/events/{private_id}/attendees/{users[1]}/revoke").status_code
        == 403
    )

    login(client, users[0])
    assert (
        client.post(f"/events/{public_id}/attendees/{users[1]}/revoke").status_code
        == 400
    )


def test_deleted_event_returns_not_found(client, users):
    login(client, users[1])
    assert client.post("/events/999999/attend").status_code == 404


def test_simultaneous_final_place_attempts_do_not_overbook(app, users, event_factory):
    event_id = event_factory(capacity=1)

    def attend(user_id):
        client = app.test_client()
        login(client, user_id)
        return client.post(f"/events/{event_id}/attend").status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(attend, users[1:]))

    assert statuses == [302, 302]
    assert attendance_count(app, event_id) == 1
