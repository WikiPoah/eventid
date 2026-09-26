from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest

from app.database.db import db
from app.database.seed import DEMO_PASSWORD, seed_demo_data
from app.models.attendance import Attendance
from app.models.event import Event
from app.models.favourite import Favourite
from app.models.user import User


class PageInputs(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.inputs = {}
        self.links = []
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("name"):
            self.inputs[values["name"]] = values.get("value", "")
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])


@pytest.fixture
def demo(app):
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        seed_demo_data()
        return {event.title: event.event_id for event in Event.query.all()}


def post_form(client, path, data=None, page=None, **kwargs):
    # The shared app fixture holds an outer context; isolate each form interaction
    # so Flask-WTF's per-request token cache cannot survive a login/session reset.
    with client.application.app_context():
        response = client.get(page or path)
        assert response.status_code == 200
        token = PageInputs(response).inputs["csrf_token"]
        return client.post(path, data={**(data or {}), "csrf_token": token}, **kwargs)


def sign_in(client, username):
    response = post_form(
        client,
        "/login",
        {"identifier": username, "password": DEMO_PASSWORD},
        follow_redirects=True,
    )
    assert b"Welcome back" in response.data


@pytest.mark.parametrize(
    "destination", ["https://example.test", "//example.test", "/\\example.test"]
)
def test_signup_does_not_follow_external_return_urls(client, destination):
    response = post_form(
        client,
        "/signup",
        {
            "first_name": "Safe",
            "last_name": "Guest",
            "username": "safe_guest",
            "email": "safe@example.test",
            "password": "Mountain!918Cloud",
            "confirm_password": "Mountain!918Cloud",
            "next": destination,
        },
    )
    assert response.status_code == 302 and response.location == "/"


def test_private_signup_return_survives_validation_error(client, demo, app):
    with app.app_context():
        event = db.session.get(Event, demo["Leipzig Organiser Planning Session"])
        destination = f"/events/{event.event_id}?" + urlencode(
            {"invite": event.invite_token}
        )
    signup_url = "/signup?" + urlencode({"next": destination})
    invalid = post_form(client, signup_url, {"first_name": "New", "next": destination})
    assert b"Please fill in all fields" in invalid.data
    assert PageInputs(invalid).inputs["next"] == destination
    response = post_form(
        client,
        signup_url,
        {
            "first_name": "New",
            "last_name": "Guest",
            "username": "new_guest",
            "email": "new@example.test",
            "password": "Mountain!918Cloud",
            "confirm_password": "Mountain!918Cloud",
            "next": destination,
        },
    )
    assert response.location == destination
    assert (
        b"Leipzig Organiser Planning Session"
        in client.get(response.location, follow_redirects=True).data
    )


def test_reseed_repairs_legacy_private_link_without_rotating_it(app, demo):
    with app.app_context():
        event = db.session.get(Event, demo["Leipzig Organiser Planning Session"])
        event.invite_token = None
        event.invite_expires_at = None
        db.session.commit()
        seed_demo_data()
        token = event.invite_token
        assert token and event.invite_expires_at == event.end_datetime
        seed_demo_data()
        assert event.invite_token == token


@pytest.mark.parametrize("state", ["full", "cancelled", "draft", "closed", "ended"])
def test_unavailable_event_cannot_create_registration(app, client, demo, state):
    event_id = demo["Berlin Morning Yoga"]
    with app.app_context():
        event = db.session.get(Event, event_id)
        if state == "full":
            event.capacity = 1
            existing_id = User.query.filter_by(username="demo_jordan").one().user_id
            db.session.add(Attendance(user_id=existing_id, event_id=event_id))
        elif state in {"cancelled", "draft"}:
            event.status = state.title()
        elif state == "closed":
            event.requests_open = False
        else:
            event.start_datetime = datetime.now() - timedelta(hours=2)
            event.end_datetime = datetime.now() - timedelta(hours=1)
        db.session.commit()
        user_id = User.query.filter_by(username="demo_tomasz").one().user_id
    sign_in(client, "demo_tomasz")
    post_form(client, f"/events/{event_id}/attend", page="/profile")
    with app.app_context():
        assert db.session.get(Attendance, (user_id, event_id)) is None
    if state == "ended":
        details = client.get(f"/events/{event_id}")
        assert b"Registration closed" in details.data
        assert f'action="/events/{event_id}/attend"'.encode() not in details.data


def test_public_signup_registration_calendar_and_ticket_journey(app, client, demo):
    event_id = demo["Berlin Morning Yoga"]
    destination = f"/events/{event_id}"
    browse = client.get("/events?search=yoga&city=Berlin")
    assert b"Berlin Morning Yoga" in browse.data
    assert b"Hamburg Street Food Social" not in browse.data
    details = client.get(destination)
    assert details.status_code == 200
    assert any(
        urlsplit(link).path == "/signup"
        and parse_qs(urlsplit(link).query).get("next") == [destination]
        for link in PageInputs(details).links
    )
    redirect = post_form(client, destination + "/attend", page="/login")
    assert "/login?next=" in redirect.location
    login_page = client.get(redirect.location)
    signup_url = "/signup?" + urlencode({"next": destination})
    assert any(
        urlsplit(link).path == "/signup"
        and parse_qs(urlsplit(link).query).get("next") == [destination]
        for link in PageInputs(login_page).links
    )
    signup_page = client.get(signup_url)
    assert PageInputs(signup_page).inputs["next"] == destination
    response = post_form(
        client,
        signup_url,
        {
            "first_name": "Recruiter",
            "last_name": "Guest",
            "username": "journey_guest",
            "email": "journey@example.test",
            "password": "Mountain!918Cloud",
            "confirm_password": "Mountain!918Cloud",
            "next": destination,
        },
    )
    assert response.location == destination
    assert b"Welcome to eventid" in client.get(response.location).data
    post_form(client, destination + "/attend", page=destination)
    duplicate = post_form(
        client, destination + "/attend", page=destination, follow_redirects=True
    )
    assert b"already attending" in duplicate.data
    with app.app_context():
        user = User.query.filter_by(username="journey_guest").one()
        assert Attendance.query.filter_by(user_id=user.user_id).count() == 1
        assert db.session.get(Attendance, (user.user_id, event_id)).status == "Going"
        event_start = db.session.get(Event, event_id).start_datetime
    assert b"Berlin Morning Yoga" in client.get("/my-events").data
    calendar_url = f"/calendar?year={event_start.year}&month={event_start.month}"
    assert b"Berlin Morning Yoga" in client.get(calendar_url).data
    ics = client.get(destination + "/calendar.ics")
    assert b"BEGIN:VEVENT" in ics.data and b"Berlin Morning Yoga" in ics.data
    assert (
        "calendar.google.com" in client.get(destination + "/calendar/google").location
    )
    assert b"Registration confirmed" in client.get(f"/my-events/{event_id}/ticket").data
    assert client.get(f"/my-events/{event_id}/ticket.png").data.startswith(b"\x89PNG")
    post_form(client, destination + "/favourite", page=destination)
    assert b"Berlin Morning Yoga" in client.get("/favourites").data
    with app.app_context():
        assert Favourite.query.filter_by(event_id=event_id).count() == 1
    post_form(client, destination + "/favourite", page=destination)
    with app.app_context():
        assert Favourite.query.filter_by(event_id=event_id).count() == 0
    assert b"journey_guest" in client.get("/profile").data
    assert client.get("/settings").status_code == 200
    outsider = app.test_client()
    sign_in(outsider, "demo_jordan")
    assert outsider.get(f"/my-events/{event_id}/ticket").status_code == 404


def test_seeded_private_invitation_approval_and_check_in_journey(app, demo):
    event_id = demo["Leipzig Organiser Planning Session"]
    destination = f"/events/{event_id}"
    with app.app_context():
        event = db.session.get(Event, event_id)
        invite = destination + "?" + urlencode({"invite": event.invite_token})
        assert event.invite_token and event.invite_expires_at
        attendee_id = User.query.filter_by(username="demo_attendee").one().user_id
    attendee = app.test_client()
    initial = attendee.get(invite)
    assert initial.status_code == 302 and "/login?next=" in initial.location
    response = post_form(
        attendee,
        initial.location,
        {"identifier": "demo_attendee", "password": DEMO_PASSWORD},
        follow_redirects=True,
    )
    assert b"Leipzig Organiser Planning Session" in response.data
    pending = post_form(
        attendee, destination + "/attend", page=destination, follow_redirects=True
    )
    assert b"Request pending" in pending.data
    assert attendee.get(f"/my-events/{event_id}/ticket").status_code == 404
    with app.app_context():
        assert db.session.get(Attendance, (attendee_id, event_id)).status == "Pending"
    organiser = app.test_client()
    sign_in(organiser, "demo_organiser")
    assert b"Leipzig Organiser Planning Session" in organiser.get("/manage-events").data
    assert organiser.get(destination + "/edit").status_code == 200
    approval = post_form(
        organiser,
        destination + f"/requests/{attendee_id}/approve",
        page=destination,
        headers={"Accept": "application/json"},
    )
    assert approval.get_json()["status"] == "Going"
    assert (
        b"Registration confirmed" in attendee.get(f"/my-events/{event_id}/ticket").data
    )
    with app.app_context():
        ticket = db.session.get(Attendance, (attendee_id, event_id)).ticket_token
    verification = organiser.get(destination + "/check-in?ticket=" + quote(ticket))
    assert b"Alice" in verification.data or b"Attendee" in verification.data
    checked = post_form(
        organiser, destination + "/check-in", {"ticket": ticket}, follow_redirects=True
    )
    assert b"checked in successfully" in checked.data
    with app.app_context():
        checked_at = db.session.get(Attendance, (attendee_id, event_id)).checked_in_at
        assert checked_at is not None
    repeated = post_form(
        organiser, destination + "/check-in", {"ticket": ticket}, follow_redirects=True
    )
    assert b"already been checked in" in repeated.data
    with app.app_context():
        assert (
            db.session.get(Attendance, (attendee_id, event_id)).checked_in_at
            == checked_at
        )
    outsider = app.test_client()
    sign_in(outsider, "demo_jordan")
    for path in ["/edit", "/check-in"]:
        assert outsider.get(destination + path).status_code == 403
    for path in [f"/requests/{attendee_id}/approve", "/check-in", "/duplicate"]:
        assert (
            post_form(
                outsider, destination + path, {"ticket": ticket}, page="/profile"
            ).status_code
            == 403
        )
    duplicate = post_form(organiser, destination + "/duplicate", page=destination)
    assert duplicate.location.endswith("/edit")
    with app.app_context():
        copied = Event.query.filter_by(
            title="Copy of Leipzig Organiser Planning Session"
        ).one()
        assert copied.status == "Draft" and not copied.requests_open
        assert not copied.attendees and copied.invite_token != event.invite_token
