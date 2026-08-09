from concurrent.futures import ThreadPoolExecutor

from app.database.db import db
from app.models.attendance import Attendance
from app.models.event import Event
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

    assert b"Registered Attendees" not in response.data

    organiser_client = app.test_client()
    login(organiser_client, users[0])
    response = organiser_client.get(f"/events/{event_id}")

    assert b"Registered Attendees" in response.data


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
