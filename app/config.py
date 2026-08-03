class Config:
    """Default application configuration."""

    # Require the application factory to provide a secret at runtime
    SECRET_KEY = None

    # Store the development database in Flask's ignored instance directory
    SQLALCHEMY_DATABASE_URI = "sqlite:///eventid.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
