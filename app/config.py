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

    # Configure page sizes and development-safe login rate-limit storage
    EVENTS_PER_PAGE = 10
    LOGIN_RATE_LIMIT = "5 per minute"
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True

    # Keep event uploads small and outside the tracked application tree
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    EVENT_IMAGE_MAX_BYTES = 4 * 1024 * 1024
    EVENT_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
