from tests.conftest import login


def test_manage_actions_are_clear_and_owner_scoped(client, users, event_factory):
    owned_id = event_factory(title="Owned Management Event", status="Published")
    event_factory(
        title="Other Management Event",
        organiser_id=users[2],
        status="Draft",
    )
    login(client, users[0])
    response = client.get("/manage-events")

    assert b"Owned Management Event" in response.data
    assert b"Other Management Event" not in response.data
    assert f"/events/{owned_id}/edit".encode() in response.data
    assert b"Edit Event" in response.data
    assert b"View Attendees" in response.data
    assert b"Export CSV" in response.data
    assert b"Move to Draft" in response.data
    assert b"Cancel Event" in response.data
    assert b">Publish</button>" not in response.data


def test_draft_and_cancelled_cards_show_relevant_status_actions(
    app, users, event_factory
):
    draft_id = event_factory(title="Draft Actions", status="Draft")
    cancelled_id = event_factory(title="Cancelled Actions", status="Cancelled")
    client = app.test_client()
    login(client, users[0])
    response = client.get("/manage-events")
    body = response.get_data(as_text=True)

    draft_card = body[body.index("Draft Actions") : body.index("Cancelled Actions")]
    assert "Publish" in draft_card
    assert "Move to Draft" not in draft_card

    cancelled_card = body[body.index("Cancelled Actions") :]
    assert "Move to Draft" in cancelled_card
    assert "Cancel Event" not in cancelled_card

    assert f"/events/{draft_id}/edit" in body
    assert f"/events/{cancelled_id}/edit" in body


def test_shared_navigation_and_key_routes_render(client, users, event_factory):
    event_id = event_factory()
    login(client, users[0])

    for path in [
        "/events",
        "/my-events",
        "/manage-events",
        f"/events/{event_id}",
        "/events/create",
        f"/events/{event_id}/edit",
    ]:
        response = client.get(path)

        assert response.status_code == 200

        assert b"Browse Events" in response.data
        assert b'href="/events"' in response.data

        assert b"My Events" in response.data
        assert b'href="/my-events"' in response.data

        assert b"Manage Events" in response.data
        assert b'href="/manage-events"' in response.data

        assert b">Attending</a>" not in response.data

        assert b"Calendar" in response.data
        assert b"Coming soon" in response.data


def test_public_event_card_has_scannable_details_action(client, users, event_factory):
    event_factory(title="Scannable Card")
    login(client, users[1])
    response = client.get("/events")

    assert b"Scannable Card" in response.data
    assert b"Date:</strong>" in response.data
    assert b"Time:</strong>" in response.data
    assert b"Venue:</strong>" in response.data
    assert b"City:</strong>" in response.data
    assert b"View Details" in response.data
