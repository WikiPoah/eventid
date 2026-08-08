from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.database.db import db
from app.models.user import User
from app.rate_limit import limiter

# Create a blueprint to handle user authentication routes

auth = Blueprint("auth", __name__)


def _safe_next_url(candidate):

    # Only allow redirects to local application paths

    if not candidate:
        return None

    parsed = urlsplit(candidate)

    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
    ):
        return None

    if (
        parsed.path.startswith("//")
        or "\\" in parsed.path
    ):
        return None

    return parsed.path + (
        f"?{parsed.query}"
        if parsed.query
        else ""
    )


def _normalize_email(value):

    if not value:
        return ""

    return value.strip().lower()


def _signup_form_values(
    first_name="",
    last_name="",
    username="",
    email="",
):

    # Keep non-sensitive signup values after validation errors

    return {
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "email": email,
    }


@auth.route("/signup", methods=["GET", "POST"])
def signup():

    # Redirect users who are already logged in

    if "user_id" in session:

        return redirect(
            url_for("home")
        )

    form_values = _signup_form_values()

    if request.method == "POST":

        # Retrieve and clean the information entered by the user

        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = _normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Keep non-sensitive information available after validation errors

        form_values = _signup_form_values(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
        )

        # Ensure all required fields have been completed

        if (
            not first_name
            or not last_name
            or not username
            or not email
            or not password
            or not confirm_password
        ):

            flash(
                "Please fill in all fields.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
            )

        # Prevent the user from registering with mismatched passwords

        if password != confirm_password:

            flash(
                "Please make sure your passwords match.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
            )

        # Keep usernames within the supported length

        if not 3 <= len(username) <= 20:

            flash(
                "Your username must be between 3 and 20 characters.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
            )

        # Retrieve matching usernames and emails

        existing_credentials = db.session.execute(
            select(
                User.username,
                User.email,
            ).where(
                or_(
                    User.username == username,
                    User.email == email,
                )
            )
        ).all()

        # Prevent duplicate usernames

        if any(
            row.username == username
            for row in existing_credentials
        ):

            flash(
                "That username is already taken.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
            )

        # Prevent duplicate email addresses

        if any(
            row.email == email
            for row in existing_credentials
        ):

            flash(
                "An account with this email already exists.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
            )

        # Securely hash the password

        password_hash = generate_password_hash(
            password
        )

        # Create the new user

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
            password_hash=password_hash,
        )

        # Save the new user

        db.session.add(new_user)

        try:

            # Flush first so the generated user ID is available before commit

            db.session.flush()

            new_user_id = new_user.user_id
            new_user_first_name = new_user.first_name

            db.session.commit()

        except IntegrityError:

            db.session.rollback()

            flash(
                "That username or email address is already in use.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
            )

        # Automatically log the new user in

        session["user_id"] = new_user_id

        flash(
            f"Welcome to eventid, {new_user_first_name}!",
            "success",
        )

        return redirect(
            url_for("home")
        )

    return render_template(
        "signup.html",
        form_values=form_values,
    )


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["LOGIN_RATE_LIMIT"],
    methods=["POST"],
)
def login():

    # Redirect users who are already logged in

    if "user_id" in session:

        return redirect(
            url_for("home")
        )

    next_url = _safe_next_url(
        request.values.get("next")
    )

    if request.method == "POST":

        # Retrieve the login credentials entered by the user

        identifier = (
            request.form.get("identifier")
            or request.form.get("username")
            or ""
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        normalized_identifier = identifier.lower()

        # Ensure both login fields have been completed

        if not identifier or not password:

            flash(
                "Please fill in all fields.",
                "error",
            )

            return render_template(
                "login.html",
                next_url=next_url,
            )

        # Look up the account associated with the entered username or email

        user = db.session.execute(
            select(User).where(
                or_(
                    User.username == normalized_identifier,
                    User.email == normalized_identifier,
                )
            )
        ).scalar_one_or_none()

        if not user:

            flash(
                "Invalid username or password.",
                "error",
            )

            return render_template(
                "login.html",
                next_url=next_url,
            )

        # Verify that the entered password matches the stored password hash

        if not check_password_hash(
            user.password_hash,
            password,
        ):

            flash(
                "Invalid username or password.",
                "error",
            )

            return render_template(
                "login.html",
                next_url=next_url,
            )

        # Store the user's ID to keep them logged in

        session["user_id"] = user.user_id

        flash(
            f"Welcome back, {user.first_name}!",
            "success",
        )

        return redirect(
            next_url or url_for("home")
        )

    return render_template(
        "login.html",
        next_url=next_url,
    )


@auth.errorhandler(429)
def login_rate_limit_exceeded(_error):

    # Display a helpful response when login attempts exceed the limit

    flash(
        "Too many login attempts. Please wait before trying again.",
        "error",
    )

    return render_template(
        "errors/429.html",
    ), 429


@auth.route("/logout", methods=["POST"])
def logout():

    # Remove the current user's session information

    session.pop(
        "user_id",
        None,
    )

    flash(
        "Logged out successfully!",
        "success",
    )

    return redirect(
        url_for("auth.login")
    )