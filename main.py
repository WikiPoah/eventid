import click
import os
from dotenv import load_dotenv
from flask import Flask, render_template, session, g
from flask_migrate import Migrate

# Load local development variables before reading the application configuration
load_dotenv()

from app.config import Config
from app.database.db import csrf, db
from app.routes.auth import auth
from app.routes.events import events
from app.models import User
from app.database.seed import seed_categories

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
    migrate.init_app(application, db)
    application.register_blueprint(auth)
    application.register_blueprint(events)

    @application.before_request
    def load_logged_in_user():
        # Load the current user once for authorization throughout the request
        g.user = db.session.get(User, session.get("user_id"))

    @application.route("/")
    def home():
        return render_template("index.html", user=g.user)

    @application.cli.command("seed-categories")
    def seed_categories_command():
        """Populate the database with the default event categories."""

        seed_categories()
        click.echo("Default event categories have been seeded.")

    return application


app = create_app()


if __name__ == "__main__":

    # Start the Flask development server
    app.run()
