from app.config import database_url
from main import create_app


def test_health_check_confirms_database(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_security_headers_are_applied(client):
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_legacy_postgres_url_is_normalized(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://user:pass@db/eventid",
    )

    assert (
        database_url()
        == "postgresql+psycopg://user:pass@db/eventid"
    )


def test_production_keeps_secure_cookie_default(monkeypatch):
    monkeypatch.setenv(
        "FLASK_ENV",
        "production",
    )

    monkeypatch.delenv(
        "SESSION_COOKIE_SECURE",
        raising=False,
    )

    monkeypatch.setenv(
        "SECRET_KEY",
        "production-config-test",
    )

    app = create_app()

    assert (
        app.config["SESSION_COOKIE_SECURE"]
        is True
    )


def test_landing_page_uses_accessible_animation_contract(client):
    response = client.get("/")

    assert (
        b'class="feature-grid stagger-grid"'
        in response.data
    )

    assert (
        b'class="skip-link"'
        in response.data
    )

    style_css = client.get(
        "/static/css/style.css"
    ).data

    responsive_css = client.get(
        "/static/css/responsive.css"
    ).data

    landing_css = client.get(
        "/static/css/landing.css"
    ).data

    combined_styles = (
        style_css
        + responsive_css
        + landing_css
    )

    assert (
        b"prefers-reduced-motion"
        in combined_styles
    )

    assert (
        b"IntersectionObserver"
        in client.get(
            "/static/js/script.js"
        ).data
    )


def test_local_artifact_patterns_are_ignored():
    ignore_rules = open(
        ".gitignore",
        encoding="utf-8",
    ).read()

    for pattern in (
        ".env",
        "instance/",
        "*.db",
        "__pycache__/",
        "*.pyc",
    ):
        assert pattern in ignore_rules