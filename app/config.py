import os


def database_url(default="sqlite:///eventid.db"):
    """Return a SQLAlchemy-compatible database URL."""

    value = os.environ.get("DATABASE_URL", default)
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


class Config:
    """Default application configuration."""

    # Require the application factory to provide a secret at runtime
    SECRET_KEY = None

    # Store the development database in Flask's ignored instance directory
    SQLALCHEMY_DATABASE_URI = database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Protect session cookies while allowing local development over HTTP
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    # Configure page sizes and development-safe login rate-limit storage
    EVENTS_PER_PAGE = 10
    LOGIN_RATE_LIMIT = "5 per minute"
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True

    # Keep event uploads small and outside the tracked application tree
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    EVENT_IMAGE_MAX_BYTES = 4 * 1024 * 1024
    EVENT_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    EVENT_IMAGE_CACHE_SECONDS = 3600
    RECOMMENDATION_LIMIT = 6
    RECOMMENDATION_CANDIDATE_LIMIT = 40
    HOMEPAGE_EVENT_LIMIT = 12

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    TRUST_PROXY = False


class DevelopmentConfig(Config):
    """Convenient local defaults; secrets are still required."""


class TestingConfig(Config):
    """Isolated defaults used by the automated test suite."""

    TESTING = True


class ProductionConfig(Config):
    """Secure defaults for an HTTPS reverse-proxy deployment."""

    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    TRUST_PROXY = True
