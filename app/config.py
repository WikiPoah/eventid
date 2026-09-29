import os
from datetime import timedelta


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
    SQLALCHEMY_DATABASE_URI = "sqlite:///eventid.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Protect session cookies while allowing local development over HTTP
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_REFRESH_EACH_REQUEST = True

    # Configure page sizes and development-safe login rate-limit storage
    EVENTS_PER_PAGE = 10
    LOGIN_RATE_LIMIT = "5 per minute"
    SIGNUP_RATE_LIMIT = "5 per hour"
    PRIVATE_LINK_RATE_LIMIT = "120 per minute"
    ATTENDANCE_RATE_LIMIT = "30 per minute"
    ACCOUNT_ACTION_RATE_LIMIT = "60 per minute"
    ORGANISER_ACTION_RATE_LIMIT = "30 per minute"
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True

    # Keep event uploads small and outside the tracked application tree
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    EVENT_IMAGE_MAX_BYTES = 4 * 1024 * 1024
    EVENT_IMAGE_MAX_PIXELS = 24_000_000
    EVENT_IMAGE_OUTPUT_SIZE = (1600, 900)
    EVENT_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    EVENT_IMAGE_CACHE_SECONDS = 3600
    RECOMMENDATION_LIMIT = 6
    RECOMMENDATION_CANDIDATE_LIMIT = 40
    HOMEPAGE_EVENT_LIMIT = 12
    EVENT_TIMEZONE = os.environ.get("EVENT_TIMEZONE", "Europe/Berlin")
    PASSWORD_MIN_LENGTH = 12
    PASSWORD_MAX_LENGTH = 128
    PASSWORD_RESET_MAX_AGE = 60 * 60
    EMAIL_VERIFICATION_MAX_AGE = 24 * 60 * 60
    RESEND_API_KEY = None
    MAIL_FROM = None
    ALLOW_DEMO_SEED = False

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    TRUST_PROXY = False


class DevelopmentConfig(Config):
    """Convenient local defaults; secrets are still required."""

    DEBUG = True


class TestingConfig(Config):
    """Isolated defaults used by the automated test suite."""

    TESTING = True
    DEBUG = False


class ProductionConfig(Config):
    """Secure defaults for an HTTPS reverse-proxy deployment."""

    SESSION_COOKIE_SECURE = True
    DEBUG = False
    PREFERRED_URL_SCHEME = "https"
    TRUST_PROXY = True
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
