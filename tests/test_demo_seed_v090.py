from datetime import datetime

from sqlalchemy import func, select
from werkzeug.security import check_password_hash

from app.database.db import db
from app.database.seed import DEMO_PASSWORD, seed_demo_data
from app.models.attendance import Attendance
from app.models.category import Category
from app.models.event import Event
from app.models.user import User
from tests.conftest import login


def test_demo_seed_cli_runs_successfully(app):
    result = app.test_cli_runner().invoke(args=["seed-demo-data"])

    assert result.exit_code == 0
    assert "Development demo data is ready" in result.output
    assert "demo_organiser" in result.output


def test_demo_seeder_is_idempotent(app):
    with app.app_context():
        first = seed_demo_data()
        first_counts = (
            User.query.count(),
            Event.query.count(),
            Category.query.count(),
            Attendance.query.count(),
        )
        second = seed_demo_data()
        second_counts = (
            User.query.count(),
            Event.query.count(),
            Category.query.count(),
            Attendance.query.count(),
        )

    assert first == {
        "users_created": 5,
        "events_created": 10,
        "attendances_created": 15,
    }
    assert second == {
        "users_created": 0,
        "events_created": 0,
        "attendances_created": 0,
    }
    assert second_counts == first_counts == (5, 10, 9, 15)


def test_seeded_users_use_hashed_development_password(app):
    with app.app_context():
        seed_demo_data()
        organiser = User.query.filter_by(username="demo_organiser").one()
        attendee = User.query.filter_by(username="demo_attendee").one()

        assert organiser.is_organiser is True
        assert attendee.is_organiser is False
        assert organiser.password_hash != DEMO_PASSWORD
        assert check_password_hash(organiser.password_hash, DEMO_PASSWORD)


def test_seeded_statuses_and_relative_dates_are_correct(app):
    with app.app_context():
        seed_demo_data()
        status_counts = dict(
            db.session.execute(
                select(Event.status, func.count()).group_by(Event.status)
            ).all()
        )
        now = datetime.now()
        upcoming_count = Event.query.filter(Event.start_datetime >= now).count()
        past_count = Event.query.filter(Event.start_datetime < now).count()

    assert status_counts == {"Cancelled": 1, "Draft": 1, "Published": 8}
    assert upcoming_count == 8
    assert past_count == 2


def test_seeded_capacity_and_attendance_scenarios(app):
    with app.app_context():
        seed_demo_data()
        nearly_full = Event.query.filter_by(title="Hamburg Community Workshop").one()
        full = Event.query.filter_by(title="Berlin Indie Music Night").one()
        unlimited = Event.query.filter_by(title="London Open Data Forum").one()

        assert nearly_full.capacity == 5
        assert len(nearly_full.attendees) == 4
        assert full.capacity == 3
        assert len(full.attendees) == 3
        assert unlimited.capacity is None
        assert len(unlimited.attendees) == 1
        assert (
            len(
                {
                    (attendance.user_id, attendance.event_id)
                    for attendance in Attendance.query.all()
                }
            )
            == Attendance.query.count()
        )


def test_city_filter_uses_only_unique_published_public_cities(app, client):
    with app.app_context():
        seed_demo_data()
        attendee_id = User.query.filter_by(username="demo_attendee").one().user_id
    login(client, attendee_id)
    response = client.get("/events")
    body = response.get_data(as_text=True)

    for city in ["Berlin", "Bremen", "Hamburg", "London", "Warsaw"]:
        assert f'<option value="{city}"' in body
        assert body.count(f'<option value="{city}"') == 1
    assert body.index('value="Berlin"') < body.index('value="Bremen"')
    assert body.index('value="Bremen"') < body.index('value="Hamburg"')
    assert 'value="Leipzig"' not in body
    assert 'value="Dresden"' not in body
    assert 'value="Cologne"' not in body


def test_seeded_demo_pages_show_expected_data(app, client):
    with app.app_context():
        seed_demo_data()
        organiser_id = User.query.filter_by(username="demo_organiser").one().user_id
        attendee_id = User.query.filter_by(username="demo_attendee").one().user_id

    login(client, attendee_id)
    browse_response = client.get("/events")
    assert b"Bremen Technology Meetup" in browse_response.data
    assert b"Bremen Makers Day Archive" not in browse_response.data
    assert b"Berlin Indie Music Night" in client.get("/my-events").data

    login(client, organiser_id)
    manage_response = client.get("/manage-events")
    assert b"Edit Event" in manage_response.data
    assert b"View Attendees" in manage_response.data
    assert b"Export CSV" in manage_response.data
    assert b"Publish" in manage_response.data
    assert b"Move to Draft" in manage_response.data
    assert b"Cancel Event" in manage_response.data
    assert b"Delete Event" in manage_response.data
