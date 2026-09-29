from urllib.parse import parse_qs, urlparse


def test_google_maps_uses_exact_coordinates(client, event_factory):
    event_id = event_factory(latitude=52.52, longitude=13.405)

    response = client.get(f"/events/{event_id}/directions/google")
    destination = urlparse(response.headers["Location"])
    query = parse_qs(destination.query)

    assert response.status_code == 302
    assert destination.netloc == "www.google.com"
    assert query["api"] == ["1"]
    assert query["destination"] == ["52.520000,13.405000"]


def test_apple_maps_falls_back_to_full_address(client, event_factory):
    event_id = event_factory(latitude=None, longitude=None)

    response = client.get(f"/events/{event_id}/directions/apple")
    destination = urlparse(response.headers["Location"])
    query = parse_qs(destination.query)

    assert response.status_code == 302
    assert destination.netloc == "maps.apple.com"
    assert query["daddr"] == ["Test Hall, 1 Test Street, 10115, Berlin, Germany"]


def test_map_provider_and_private_access_are_restricted(client, event_factory):
    public_id = event_factory()
    private_id = event_factory(privacy="Private")

    assert client.get(f"/events/{public_id}/directions/unknown").status_code == 404
    assert client.get(f"/events/{private_id}/directions/google").status_code == 403


def test_public_details_show_map_and_share_controls(client, event_factory):
    event_id = event_factory(latitude=52.52, longitude=13.405)

    response = client.get(f"/events/{event_id}")

    assert response.status_code == 200
    assert b"Google Maps" in response.data
    assert b"Apple Maps" in response.data
    assert b'class="event-map-preview"' in response.data
    assert b"https://www.google.com/maps?" in response.data
    assert b"q=52.520000%2C13.405000&amp;output=embed" in response.data
    assert b"Exact location: 52.52000, 13.40500" in response.data
    assert b"Copy Link" in response.data
    assert b"WhatsApp" in response.data
    assert b"data-share-event" in response.data
