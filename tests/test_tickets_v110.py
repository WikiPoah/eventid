from datetime import UTC, datetime
from html.parser import HTMLParser

import pytest

from app.database.db import db
from app.models.attendance import Attendance
from tests.conftest import login


def test_confirmed_attendee_can_view_ticket_and_qr(app, client, users, event_factory):
    event_id = event_factory(title="Ticketed Event")
    with app.app_context():
        db.session.add(Attendance(user_id=users[1], event_id=event_id, status="Going"))
        db.session.commit()

    login(client, users[1])
    ticket = client.get(f"/my-events/{event_id}/ticket")
    qr = client.get(f"/my-events/{event_id}/ticket.png")

    assert ticket.status_code == 200
    assert b"Registration confirmed" in ticket.data
    assert b"Ticketed Event" in ticket.data
    assert f"/my-events/{event_id}/ticket.png".encode() in ticket.data
    assert qr.status_code == 200
    assert qr.mimetype == "image/png"
    assert qr.data.startswith(b"\x89PNG")
    assert qr.headers["Cache-Control"] == "private, no-store"


def test_pending_or_other_user_cannot_view_ticket(app, client, users, event_factory):
    event_id = event_factory(privacy="Private")
    with app.app_context():
        db.session.add(
            Attendance(user_id=users[1], event_id=event_id, status="Pending")
        )
        db.session.commit()

    login(client, users[1])
    assert client.get(f"/my-events/{event_id}/ticket").status_code == 404

    login(client, users[2])
    assert client.get(f"/my-events/{event_id}/ticket.png").status_code == 404


def test_organiser_checks_in_ticket_once(app, client, users, event_factory):
    event_id = event_factory(title="Check-In Event")
    with app.app_context():
        attendance = Attendance(user_id=users[1], event_id=event_id, status="Going")
        db.session.add(attendance)
        db.session.commit()
        ticket_token = attendance.ticket_token

    login(client, users[0])
    preview = client.get(f"/events/{event_id}/check-in?ticket={ticket_token}")
    first = client.post(
        f"/events/{event_id}/check-in",
        data={"ticket": ticket_token},
        follow_redirects=True,
    )
    second = client.post(
        f"/events/{event_id}/check-in",
        data={"ticket": ticket_token},
        follow_redirects=True,
    )

    assert preview.status_code == 200
    assert b"Alice Attendee" in preview.data
    assert b"Ready to check in" in preview.data
    assert b"checked in successfully" in first.data
    assert b"already been checked in" in second.data
    with app.app_context():
        assert (
            db.session.get(Attendance, (users[1], event_id)).checked_in_at is not None
        )


def test_non_organiser_cannot_use_check_in(client, users, event_factory):
    event_id = event_factory()
    login(client, users[1])

    assert client.get(f"/events/{event_id}/check-in").status_code == 403


def test_my_events_links_to_ticket(app, client, users, event_factory):
    event_id = event_factory(title="My Ticket Event")
    with app.app_context():
        db.session.add(Attendance(user_id=users[1], event_id=event_id, status="Going"))
        db.session.commit()

    login(client, users[1])
    response = client.get("/my-events")

    assert response.status_code == 200
    assert b"View confirmation and QR ticket" in response.data
    assert f"/my-events/{event_id}/ticket".encode() in response.data


def test_check_in_dashboard_supports_manual_check_in_and_undo(
    app, client, users, event_factory
):
    event_id = event_factory(title="Dashboard Event")
    with app.app_context():
        db.session.add(Attendance(user_id=users[1], event_id=event_id, status="Going"))
        db.session.commit()

    login(client, users[0])
    dashboard = client.get(f"/events/{event_id}/check-in")
    checked = client.post(
        f"/events/{event_id}/check-in",
        data={"action": "check_in", "user_id": users[1]},
        follow_redirects=True,
    )
    undone = client.post(
        f"/events/{event_id}/check-in",
        data={"action": "undo", "user_id": users[1]},
        follow_redirects=True,
    )

    assert b"Attendee list" in dashboard.data
    assert b"Alice Attendee" in dashboard.data
    assert b"Still expected" in dashboard.data
    assert b"checked in successfully" in checked.data
    assert b"check-in was undone" in undone.data
    with app.app_context():
        assert db.session.get(Attendance, (users[1], event_id)).checked_in_at is None


def test_check_in_dashboard_searches_attendees(app, client, users, event_factory):
    event_id = event_factory()
    with app.app_context():
        db.session.add_all(
            [
                Attendance(user_id=users[1], event_id=event_id, status="Going"),
                Attendance(user_id=users[2], event_id=event_id, status="Going"),
            ]
        )
        db.session.commit()

    login(client, users[0])
    response = client.get(f"/events/{event_id}/check-in?search=alice")

    assert b"Alice Attendee" in response.data
    assert b"Oscar Other" not in response.data


@pytest.mark.parametrize(("total", "checked"), [(0, 0), (2, 0), (2, 1), (2, 2)])
def test_check_in_progress_works_under_strict_csp(
    app, client, users, event_factory, total, checked
):
    event_id = event_factory()
    with app.app_context():
        for index, user_id in enumerate(users[1:][:total]):
            db.session.add(
                Attendance(
                    user_id=user_id,
                    event_id=event_id,
                    status="Going",
                    checked_in_at=datetime.now(UTC) if index < checked else None,
                )
            )
        db.session.commit()
    login(client, users[0])
    response = client.get(f"/events/{event_id}/check-in")

    class ProgressParser(HTMLParser):
        progress = []

        def handle_starttag(self, tag, attrs):
            assert "style" not in dict(attrs)
            if tag == "progress":
                self.progress.append(dict(attrs))

    parser = ProgressParser()
    parser.feed(response.get_data(as_text=True))
    assert len(parser.progress) == 1
    assert parser.progress[0]["value"] == str(checked)
    assert parser.progress[0]["max"] == str(total or 1)
    assert "style-src 'self';" in response.headers["Content-Security-Policy"]
