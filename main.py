import click
import os
from dotenv import load_dotenv
from flask import Flask, render_template, session, g
from flask_migrate import Migrate

# Load local development variables before reading the application configuration
load_dotenv()

from app.config import Config
from app.database.db import csrf, db
from app.rate_limit import limiter
from app.routes.auth import auth
from app.routes.events import events
from app.models import User
from app.database.seed import seed_categories, seed_demo_data, DEMO_PASSWORD

migrate = Migrate()


def create_app(test_config=None):
    """Create and configure an EventID application instance."""

    application = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="app/templates",
        static_folder="app/static",
    )
    application.config.from_object(Config)

    # Allow environment variables to override development-safe defaults
    application.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            Config.SQLALCHEMY_DATABASE_URI,
        ),
        LOGIN_RATE_LIMIT=os.environ.get(
            "LOGIN_RATE_LIMIT",
            Config.LOGIN_RATE_LIMIT,
        ),
        RATELIMIT_STORAGE_URI=os.environ.get(
            "RATELIMIT_STORAGE_URI",
            Config.RATELIMIT_STORAGE_URI,
        ),
        SESSION_COOKIE_SECURE=os.environ.get(
            "SESSION_COOKIE_SECURE",
            "false",
        ).lower() in {"1", "true", "yes", "on"},
        MAX_CONTENT_LENGTH=int(os.environ.get(
            "MAX_CONTENT_LENGTH",
            Config.MAX_CONTENT_LENGTH,
        )),
    )
    application.config.setdefault(
        "EVENT_IMAGE_UPLOAD_FOLDER",
        os.path.join(application.instance_path, "event_images"),
    )

    if test_config:
        application.config.update(test_config)

    # Refuse to start without a secret instead of using a predictable fallback
    if not application.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is required. Set it in the environment or a local .env file."
        )

    # Let concurrent SQLite attendance requests wait for the active writer
    if application.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        application.config.setdefault(
            "SQLALCHEMY_ENGINE_OPTIONS",
            {"connect_args": {"timeout": 30}},
        )

    # Connect extensions and route blueprints to this application instance
    db.init_app(application)
    csrf.init_app(application)
    limiter.init_app(application)
    migrate.init_app(application, db)
    application.register_blueprint(auth)
    application.register_blueprint(events)

    @application.before_request
    def load_logged_in_user():
        # Load the current user once for authorization throughout the request
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id is not None else None

    @application.route("/")
    def home():
        return render_template("index.html", user=g.user)

    # Render safe, consistent pages for expected HTTP failures
    @application.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @application.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @application.errorhandler(429)
    def too_many_requests(_error):
        return render_template("errors/429.html"), 429

    @application.errorhandler(500)
    def internal_server_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @application.cli.command("seed-categories")
    def seed_categories_command():
        """Populate the database with the default event categories."""

        seed_categories()
        click.echo("Default event categories have been seeded.")

    @application.cli.command("seed-demo-data")
    def seed_demo_data_command():
        """Populate development-only users, events, and attendance."""

        result = seed_demo_data()
        click.echo(
            "Development demo data is ready "
            f"({result['users_created']} users, "
            f"{result['events_created']} events, and "
            f"{result['attendances_created']} registrations created)."
        )
        click.echo(
            "Demo logins: demo_organiser or demo_attendee; "
            f"development-only password: {DEMO_PASSWORD}"
        )

    return application


app = create_app()


if __name__ == "__main__":

    # Start the Flask development server
    app.run()
