from datetime import datetime, timedelta

from sqlalchemy import event as sqlalchemy_event

from app.database.db import db
from app.models.attendance import Attendance
from app.models.user import User
from tests.conftest import login


def test_dashboard_summarizes_only_organisers_events(app, client, users, event_factory):
    upcoming_id = event_factory(
        title="Nearly Full Event",
        capacity=5,
        start_datetime=datetime.now() + timedelta(days=2),
    )
    full_id = event_factory(
        title="Full Event",
        capacity=1,
        start_datetime=datetime.now() + timedelta(days=3),
    )
    unlimited_id = event_factory(
        title="Unlimited Event",
        capacity=None,
        start_datetime=datetime.now() + timedelta(days=4),
    )
    event_factory(
        title="Past Event",
        start_datetime=datetime.now() - timedelta(days=2),
        end_datetime=datetime.now() - timedelta(days=2) + timedelta(hours=1),
    )
    event_factory(
        title="Other Organiser Event",
        organiser_id=users[2],
        start_datetime=datetime.now() + timedelta(days=5),
    )

    with app.app_context():
        additional_users = [
            User(
                first_name=f"Attendee{number}",
                last_name="Dashboard",
                username=f"dashboard{number}",
                email=f"dashboard{number}@example.test",
                password_hash="unused",
            )
            for number in range(4)
        ]
        db.session.add_all(additional_users)
        db.session.flush()
        db.session.add_all(
            [
                Attendance(user_id=user.user_id, event_id=upcoming_id)
                for user in additional_users
            ]
            + [Attendance(user_id=users[1], event_id=full_id)]
            + [Attendance(user_id=users[2], event_id=unlimited_id)]
        )
        db.session.commit()

    login(client, users[0])
    response = client.get("/manage-events")

    assert response.status_code == 200
    assert b"Total events:</strong> 4" in response.data
    assert b"Upcoming events:</strong> 3" in response.data
    assert b"Past events:</strong> 1" in response.data
    assert b"Total registrations:</strong> 6" in response.data
    assert b"Full events:</strong> 1" in response.data
    assert b"Nearly full events:</strong> 1" in response.data
    assert b"Other Organiser Event" not in response.data
    assert b"4 / 5 attending" in response.data
    assert b"1 attending (unlimited capacity)" in response.data


def test_dashboard_query_count_does_not_grow_per_event(
    app, client, users, event_factory
):
    for number in range(6):
        event_factory(title=f"Dashboard Event {number}")

    select_count = 0

    def count_selects(_connection, _cursor, statement, *_args):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    login(client, users[0])
    with app.app_context():
        sqlalchemy_event.listen(
            db.engine,
            "before_cursor_execute",
            count_selects,
        )
        try:
            response = client.get("/manage-events")
        finally:
            sqlalchemy_event.remove(
                db.engine,
                "before_cursor_execute",
                count_selects,
            )

    assert response.status_code == 200
    assert select_count <= 3


def test_dashboard_requires_authentication(client):
    response = client.get("/manage-events")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login?next=/manage-events")


def test_my_events_and_manage_events_keep_distinct_responsibilities(
    app, client, users, event_factory
):
    organised_id = event_factory(title="My Organised Event")
    attended_id = event_factory(
        title="My Attended Event",
        organiser_id=users[2],
    )
    with app.app_context():
        db.session.add(Attendance(user_id=users[0], event_id=attended_id))
        db.session.commit()

    login(client, users[0])
    my_events_response = client.get("/my-events")
    manage_response = client.get("/manage-events")

    assert b"My Attended Event" in my_events_response.data
    assert b"My Organised Event" not in my_events_response.data
    assert b"My Organised Event" in manage_response.data
    assert b"My Attended Event" not in manage_response.data

    with app.app_context():
        assert (
            Attendance.query.filter_by(
                user_id=users[0],
                event_id=organised_id,
            ).first()
            is None
        )


def test_users_cannot_see_another_organisers_dashboard_data(
    client, users, event_factory
):
    event_factory(title="First Organiser Private Dashboard Event")
    event_factory(
        title="Second Organiser Dashboard Event",
        organiser_id=users[2],
    )

    login(client, users[2])
    response = client.get("/manage-events")

    assert b"Second Organiser Dashboard Event" in response.data
    assert b"First Organiser Private Dashboard Event" not in response.data


def test_navigation_links_to_each_page_responsibility(client, users):
    login(client, users[0])
    response = client.get("/")

    assert b'href="/events">Browse Events</a>' in response.data
    assert b'href="/my-events">My Events</a>' in response.data
    assert b'href="/manage-events">Manage Events</a>' in response.data
    assert b"/my-attending-events" not in response.data
    assert b">Attending</a>" not in response.data
    assert b">Calendar</a>" in response.data
