import hashlib
import os
from logging.config import dictConfig

import click
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    g,
    jsonify,
    render_template,
    request,
    session,
)
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError
from sqlalchemy import select, text
from werkzeug.middleware.proxy_fix import ProxyFix

# Load local development variables before reading the application configuration
load_dotenv()

from app.config import DevelopmentConfig, ProductionConfig, TestingConfig, database_url
from app.database.db import csrf, db
from app.database.seed import DEMO_PASSWORD, seed_categories, seed_demo_data
from app.discovery import public_homepage_events
from app.models import User, UserSession
from app.rate_limit import limiter
from app.recommendations import recommended_events
from app.routes.auth import auth
from app.routes.events import events

migrate = Migrate()


def create_app(test_config=None):
    """Bind extensions and routes after applying environment and test overrides.

    Normalize database URLs here, before SQLAlchemy sees them. Explicit test
    configuration wins so a production environment cannot redirect test writes.
    """

    application = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="app/templates",
        static_folder="app/static",
    )
    environment = os.environ.get("FLASK_ENV", "development").lower()
    config_class = (
        ProductionConfig if environment == "production" else DevelopmentConfig
    )
    if test_config:
        config_class = TestingConfig
    application.config.from_object(config_class)

    # Allow environment variables to override development-safe defaults
    application.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=database_url(config_class.SQLALCHEMY_DATABASE_URI),
        LOGIN_RATE_LIMIT=os.environ.get(
            "LOGIN_RATE_LIMIT",
            config_class.LOGIN_RATE_LIMIT,
        ),
        SIGNUP_RATE_LIMIT=os.environ.get(
            "SIGNUP_RATE_LIMIT", config_class.SIGNUP_RATE_LIMIT
        ),
        PRIVATE_LINK_RATE_LIMIT=os.environ.get(
            "PRIVATE_LINK_RATE_LIMIT", config_class.PRIVATE_LINK_RATE_LIMIT
        ),
        ATTENDANCE_RATE_LIMIT=os.environ.get(
            "ATTENDANCE_RATE_LIMIT", config_class.ATTENDANCE_RATE_LIMIT
        ),
        ACCOUNT_ACTION_RATE_LIMIT=os.environ.get(
            "ACCOUNT_ACTION_RATE_LIMIT", config_class.ACCOUNT_ACTION_RATE_LIMIT
        ),
        ORGANISER_ACTION_RATE_LIMIT=os.environ.get(
            "ORGANISER_ACTION_RATE_LIMIT", config_class.ORGANISER_ACTION_RATE_LIMIT
        ),
        RATELIMIT_STORAGE_URI=os.environ.get(
            "RATELIMIT_STORAGE_URI",
            os.environ.get(
                "RATE_LIMIT_STORAGE_URI",
                config_class.RATELIMIT_STORAGE_URI,
            ),
        ),
        SESSION_COOKIE_SECURE=os.environ.get(
            "SESSION_COOKIE_SECURE",
            str(config_class.SESSION_COOKIE_SECURE),
        ).lower()
        in {"1", "true", "yes", "on"},
        MAX_CONTENT_LENGTH=int(
            os.environ.get(
                "MAX_CONTENT_LENGTH",
                config_class.MAX_CONTENT_LENGTH,
            )
        ),
        RESEND_API_KEY=os.environ.get("RESEND_API_KEY"),
        MAIL_FROM=os.environ.get("MAIL_FROM"),
        ALLOW_DEMO_SEED=os.environ.get("ALLOW_DEMO_SEED", "false").lower()
        in {"1", "true", "yes", "on"},
    )
    application.config["EVENT_IMAGE_UPLOAD_FOLDER"] = os.environ.get(
        "UPLOAD_DIRECTORY",
        application.config.get("EVENT_IMAGE_UPLOAD_FOLDER")
        or os.path.join(application.instance_path, "event_images"),
    )

    if test_config:
        application.config.update(test_config)

    # Refuse to start without a secret instead of using a predictable fallback
    if not application.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is required. Set it in the environment or a local .env file."
        )

    if (
        environment == "production"
        and not application.testing
        and not os.environ.get("DATABASE_URL")
    ):
        raise RuntimeError("DATABASE_URL is required in production.")

    if (
        environment == "production"
        and application.config["RATELIMIT_STORAGE_URI"] == "memory://"
    ):
        application.logger.warning(
            "In-memory rate limiting is not shared across production instances."
        )

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": application.config["LOG_LEVEL"],
            },
        }
    )

    # Trust exactly one forwarding proxy, as in the Render deployment. Do not
    # expose this production configuration directly to untrusted client headers.
    if application.config.get("TRUST_PROXY"):
        application.wsgi_app = ProxyFix(
            application.wsgi_app, x_for=1, x_proto=1, x_host=1
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
        # auth_version invalidates all old cookies after a password change;
        # tracked token hashes additionally allow revoking one device at a time.
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id is not None else None
        if g.user is not None and session.get("auth_version") != g.user.auth_version:
            session.clear()
            g.user = None
        if g.user is not None and session.get("session_token"):
            token_hash = hashlib.sha256(session["session_token"].encode()).hexdigest()
            tracked_session = db.session.scalar(
                select(UserSession).where(
                    UserSession.token_hash == token_hash,
                    UserSession.user_id == g.user.user_id,
                    UserSession.revoked_at.is_(None),
                )
            )
            if tracked_session is None:
                session.clear()
                g.user = None

    @application.route("/")
    def home():
        this_week_events, more_upcoming_events = public_homepage_events(
            limit=application.config["HOMEPAGE_EVENT_LIMIT"]
        )
        recommendations = []
        show_recommendations = g.user is not None
        if show_recommendations:
            recommendations = recommended_events(
                g.user.user_id,
                limit=application.config["RECOMMENDATION_LIMIT"],
                candidate_limit=application.config["RECOMMENDATION_CANDIDATE_LIMIT"],
            )
        return render_template(
            "index.html",
            user=g.user,
            this_week_events=this_week_events,
            more_upcoming_events=more_upcoming_events,
            recommendations=recommendations,
            show_recommendations=show_recommendations,
        )

    @application.get("/favicon.ico")
    def favicon():
        return application.send_static_file("images/logo.png")

    @application.get("/health")
    def health():
        """Confirm application and database availability without exposing internals."""

        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            db.session.rollback()
            application.logger.exception("Health check database query failed")
            return jsonify(status="unhealthy"), 503
        return jsonify(status="ok"), 200

    @application.after_request
    def add_security_headers(response):
        """Apply a practical baseline policy to every application response."""

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; font-src 'self'; form-action 'self'; "
            "frame-src https://www.google.com; "
            "frame-ancestors 'none'; base-uri 'self'",
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), camera=(), microphone=()"
        )
        if request.endpoint in {
            "auth.forgot_password",
            "auth.reset_password",
            "auth.verify_email",
            "auth.settings",
        }:
            response.headers["Cache-Control"] = "private, no-store"
        if application.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

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

    @application.errorhandler(CSRFError)
    def csrf_error(_error):
        """Recover safely when a form was left open beyond its session lifetime."""

        message = "Your form expired. Please review it and submit again."
        if request.endpoint == "auth.login":
            flash(message, "warning")
            return (
                render_template(
                    "login.html",
                    next_url=request.args.get("next", ""),
                    identifier=(
                        request.form.get("identifier")
                        or request.form.get("username")
                        or ""
                    ).strip(),
                ),
                400,
            )
        if request.endpoint == "auth.signup":
            flash(message, "warning")
            return (
                render_template(
                    "signup.html",
                    form_values={
                        "first_name": request.form.get("first_name", "").strip(),
                        "last_name": request.form.get("last_name", "").strip(),
                        "username": request.form.get("username", "").strip(),
                        "email": request.form.get("email", "").strip(),
                    },
                ),
                400,
            )
        return render_template("errors/400.html", message=message), 400

    @application.errorhandler(500)
    def internal_server_error(_error):
        db.session.rollback()
        application.logger.error("Unhandled server error", exc_info=_error)
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
