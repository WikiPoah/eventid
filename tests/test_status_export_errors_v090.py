import csv
from io import StringIO

from app.database.db import db
from app.models.attendance import Attendance
from tests.conftest import login


def test_draft_and_cancelled_events_are_not_browsable(
    app, client, users, event_factory
):
    draft_id = event_factory(title="Hidden Draft", status="Draft")
    cancelled_id = event_factory(title="Hidden Cancelled", status="Cancelled")
    event_factory(title="Visible Published", status="Published")
    login(client, users[1])
    response = client.get("/events")
    assert b"Visible Published" in response.data
    assert b"Hidden Draft" not in response.data
    assert b"Hidden Cancelled" not in response.data
    assert client.get(f"/events/{draft_id}").status_code == 403
    assert client.get(f"/events/{cancelled_id}").status_code == 403


def test_cancelled_event_rejects_new_attendance_but_remains_for_attendee(
    app, users, event_factory
):
    event_id = event_factory(title="Cancelled Registration", status="Cancelled")
    with app.app_context():
        db.session.add(Attendance(user_id=users[1], event_id=event_id))
        db.session.commit()

    attendee_client = app.test_client()
    login(attendee_client, users[1])
    response = attendee_client.get("/my-events")
    assert b"Cancelled Registration" in response.data
    assert b"Cancelled" in response.data
    assert attendee_client.get(f"/events/{event_id}").status_code == 200

    other_client = app.test_client()
    login(other_client, users[2])
    response = other_client.post(
        f"/events/{event_id}/attend",
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert Attendance.query.filter_by(event_id=event_id).count() == 1


def test_organiser_can_view_draft_and_cancelled_events(client, users, event_factory):
    draft_id = event_factory(status="Draft")
    cancelled_id = event_factory(status="Cancelled")
    login(client, users[0])
    assert client.get(f"/events/{draft_id}").status_code == 200
    assert client.get(f"/events/{cancelled_id}").status_code == 200


def test_attendee_csv_is_owner_only_and_excludes_sensitive_fields(
    app, client, users, event_factory
):
    event_id = event_factory()
    with app.app_context():
        db.session.add(Attendance(user_id=users[1], event_id=event_id))
        db.session.commit()

    login(client, users[1])
    assert client.get(f"/events/{event_id}/attendees/export").status_code == 403
    login(client, users[0])
    response = client.get(f"/events/{event_id}/attendees/export")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    rows = list(csv.reader(StringIO(response.get_data(as_text=True))))
    assert rows[0] == [
        "First name",
        "Last name",
        "Username",
        "Registration date",
        "Attendance status",
    ]
    assert rows[1][0:3] == ["Alice", "Attendee", "attendee"]
    assert "password" not in response.get_data(as_text=True).lower()
    assert "attendee@example.test" not in response.get_data(as_text=True)


def test_custom_error_pages_render(app, client, users):
    assert b"Page not found" in client.get("/missing-page").data
    login(client, users[0])
    response = client.get("/events/999999")
    assert response.status_code == 404
    assert b"Page not found" in response.data
    with app.test_request_context():
        response = app.handle_http_exception(
            __import__("werkzeug").exceptions.Forbidden()
        )
        response = app.make_response(response)
        assert response.status_code == 403
        assert b"Access denied" in response.get_data()
        response = app.handle_http_exception(
            __import__("werkzeug").exceptions.InternalServerError()
        )
        response = app.make_response(response)
        assert response.status_code == 500
        assert b"Something went wrong" in response.get_data()
