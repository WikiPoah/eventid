from datetime import datetime, timedelta

from app.models.attendance import Attendance


def login(client, user):
    with client.session_transaction() as session:
        session["user_id"] = user


def test_calendar_requires_login(client):
    response = client.get("/calendar")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?next=/calendar")


def test_calendar_includes_attended_and_owned_without_duplicates(
    app, client, users, event_factory
):
    organiser, attendee, other = users
    now = datetime.now()
    attended = event_factory(
        title="Attended Calendar Event",
        organiser_id=other,
        start_datetime=now + timedelta(days=2),
        end_datetime=now + timedelta(days=2, hours=2),
    )
    event_factory(
        title="Owned Calendar Event",
        organiser_id=attendee,
        start_datetime=now + timedelta(days=3),
        end_datetime=now + timedelta(days=3, hours=2),
        status="Draft",
    )
    overlap = event_factory(
        title="Owned And Attended",
        organiser_id=attendee,
        start_datetime=now + timedelta(days=4),
        end_datetime=now + timedelta(days=4, hours=2),
        status="Published",
    )
    with app.app_context():
        from app.database.db import db

        db.session.add_all(
            [
                Attendance(user_id=attendee, event_id=attended),
                Attendance(user_id=attendee, event_id=overlap),
            ]
        )
        db.session.commit()
    login(client, attendee)
    response = client.get("/calendar")
    assert response.status_code == 200
    assert response.data.count(b"Owned And Attended") == 1
    assert b"Attended Calendar Event" in response.data
    assert b"Owned Calendar Event" in response.data
    assert b"Other Private" not in response.data


def test_calendar_keeps_cancelled_attendance_visible_and_separates_past(
    client, users, event_factory
):
    organiser, attendee, _ = users
    cancelled = event_factory(
        title="Cancelled Schedule",
        organiser_id=organiser,
        status="Cancelled",
        start_datetime=datetime.now() + timedelta(days=1),
        end_datetime=datetime.now() + timedelta(days=1, hours=2),
    )
    past = event_factory(
        title="Past Schedule",
        organiser_id=organiser,
        start_datetime=datetime.now() - timedelta(days=3),
        end_datetime=datetime.now() - timedelta(days=3) + timedelta(hours=2),
    )
    from app.database.db import db

    db.session.add_all(
        [
            Attendance(user_id=attendee, event_id=cancelled),
            Attendance(user_id=attendee, event_id=past),
        ]
    )
    db.session.commit()
    login(client, attendee)
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b"Cancelled Schedule" in response.data
    assert b"Past Schedule" in response.data
    assert b"Cancelled" in response.data
    assert b"/events/" in response.data
