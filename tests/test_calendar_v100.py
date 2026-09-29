from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app.database.db import db
from app.models.attendance import Attendance
from tests.conftest import login


def test_calendar_requires_login(client):
    response = client.get("/calendar")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_calendar_renders_month_view(client, users):
    login(client, users[1])

    response = client.get("/calendar")

    assert response.status_code == 200
    assert b"Calendar" in response.data
    assert b"Your schedule" in response.data
    assert b"Today" in response.data
    assert b"Organising" in response.data
    assert b"Attending" in response.data
    assert b'role="grid"' in response.data


def test_calendar_does_not_expose_unrelated_events(client, users, event_factory):
    event_factory(title="Hidden Calendar Event")

    login(client, users[1])

    response = client.get("/calendar")

    assert response.status_code == 200
    assert b"Hidden Calendar Event" not in response.data


def test_calendar_shows_attending_and_organised_events(
    app, client, users, event_factory
):
    attending_id = event_factory(title="Attending Event")
    event_factory(
        title="Organised Event",
        organiser_id=users[1],
    )
    with app.app_context():
        db.session.add(
            Attendance(user_id=users[1], event_id=attending_id, status="Going")
        )
        db.session.commit()

    login(client, users[1])
    response = client.get("/calendar")

    assert response.status_code == 200
    assert b"Attending Event" in response.data
    assert b"Organised Event" in response.data
    assert b"calendar-event-attending" in response.data
    assert b"calendar-event-organising" in response.data


def test_calendar_month_navigation_and_invalid_dates(client, users):
    login(client, users[1])

    response = client.get("/calendar?year=2026&month=12")

    assert response.status_code == 200
    assert b"December 2026" in response.data
    assert b"year=2027&amp;month=1" in response.data
    assert b"year=2026&amp;month=11" in response.data
    assert client.get("/calendar?year=2026&month=13").status_code == 404


def test_public_event_downloads_portable_ics(client, event_factory):
    start = datetime(2026, 8, 20, 18, 30)
    end = datetime(2026, 8, 20, 20, 0)
    event_id = event_factory(
        title="Calendar, Test; Event",
        description="First line\nSecond line",
        venue_name="Test Hall",
        address="1 Example Street",
        postcode="10115",
        city="Berlin",
        start_datetime=start,
        end_datetime=end,
    )

    response = client.get(f"/events/{event_id}/calendar.ics")

    expected_start = start.replace(tzinfo=ZoneInfo("Europe/Berlin")).astimezone(
        ZoneInfo("UTC")
    )
    assert response.status_code == 200
    assert response.mimetype == "text/calendar"
    assert response.headers["Content-Disposition"] == (
        f'attachment; filename="event-{event_id}.ics"'
    )
    assert b"BEGIN:VCALENDAR\r\n" in response.data
    assert b"SUMMARY:Calendar\\, Test\\; Event" in response.data
    assert b"DESCRIPTION:First line\\nSecond line" in response.data
    assert (
        f"DTSTART:{expected_start.strftime('%Y%m%dT%H%M%SZ')}".encode() in response.data
    )
    assert (
        b"LOCATION:Test Hall\\, 1 Example Street\\, 10115\\, Berlin\\, Germany"
        in response.data
    )


def test_private_calendar_requires_event_access(app, client, users, event_factory):
    event_id = event_factory(privacy="Private")

    assert client.get(f"/events/{event_id}/calendar.ics").status_code == 403

    with app.app_context():
        db.session.add(Attendance(user_id=users[1], event_id=event_id, status="Going"))
        db.session.commit()
    login(client, users[1])

    assert client.get(f"/events/{event_id}/calendar.ics").status_code == 200


def test_event_details_offers_calendar_download(client, event_factory):
    event_id = event_factory()
    response = client.get(f"/events/{event_id}")

    assert b"Add to Calendar" in response.data
    assert b"Google Calendar" in response.data
    assert b"Apple Calendar (.ics)" in response.data
    assert b"Outlook Calendar" in response.data
    assert f"/events/{event_id}/calendar.ics".encode() in response.data


def test_google_calendar_opens_pre_filled_event(client, event_factory):
    event_id = event_factory(title="Google Calendar Test")

    response = client.get(f"/events/{event_id}/calendar/google")
    destination = urlparse(response.headers["Location"])
    query = parse_qs(destination.query)

    assert response.status_code == 302
    assert destination.netloc == "calendar.google.com"
    assert query["action"] == ["TEMPLATE"]
    assert query["text"] == ["Google Calendar Test"]
    assert "dates" in query


def test_outlook_calendar_opens_pre_filled_event(client, event_factory):
    event_id = event_factory(title="Outlook Calendar Test")

    response = client.get(f"/events/{event_id}/calendar/outlook")
    destination = urlparse(response.headers["Location"])
    query = parse_qs(destination.query)

    assert response.status_code == 302
    assert destination.netloc == "outlook.live.com"
    assert query["rru"] == ["addevent"]
    assert query["subject"] == ["Outlook Calendar Test"]
    assert query["startdt"][0].endswith("+02:00")


def test_unknown_calendar_provider_is_not_found(client, event_factory):
    event_id = event_factory()

    assert client.get(f"/events/{event_id}/calendar/unknown").status_code == 404
