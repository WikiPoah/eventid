from tests.conftest import login


def test_calendar_requires_login(client):
    response = client.get("/calendar")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_calendar_renders_coming_soon_state(client, users):
    login(client, users[1])

    response = client.get("/calendar")

    assert response.status_code == 200
    assert b"Calendar" in response.data
    assert b"Coming soon" in response.data
    assert b"Calendar is coming soon" in response.data
    assert b"View My Events" in response.data


def test_calendar_does_not_expose_unfinished_schedule(client, users, event_factory):
    event_factory(
        title="Hidden Calendar Event"
    )

    login(client, users[1])

    response = client.get("/calendar")

    assert response.status_code == 200
    assert b"Hidden Calendar Event" not in response.data
    assert b"Calendar is coming soon" in response.data