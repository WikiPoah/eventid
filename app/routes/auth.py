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
    """Return a local application path or reject an external redirect."""

    if not candidate:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    if parsed.path.startswith("//") or "\\" in parsed.path:
        return None
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


@auth.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        # Retrieve and clean the information entered by the user
        first_name = request.form["first_name"].strip()
        last_name = request.form["last_name"].strip()
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Ensure all required fields have been completed
        if (
            not first_name
            or not last_name
            or not username
            or not email
            or not password
            or not confirm_password
        ):

            flash("Please fill in all fields.")

            return render_template("signup.html")

        # Prevent the user from registering with mismatched passwords
        if password != confirm_password:

            flash("Please make sure your passwords match.")

            return render_template("signup.html")

        # Keep usernames within the length supported by the database model
        if not 3 <= len(username) <= 20:
            flash("Your username must be between 3 and 20 characters.")
            return render_template("signup.html")

        # Retrieve matching usernames and emails with one indexed query
        existing_credentials = db.session.execute(
            select(User.username, User.email).where(
                or_(User.username == username, User.email == email)
            )
        ).all()

        if any(row.username == username for row in existing_credentials):

            flash("That username is already taken.")

            return render_template("signup.html")

        if any(row.email == email for row in existing_credentials):

            flash("An account with this email already exists.")

            return render_template("signup.html")

        # Securely hash the password before storing it
        password_hash = generate_password_hash(password)

        # Create a new user record with the submitted details
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
            password_hash=password_hash,
        )

        # Save the new user to the database
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            # Roll back conflicts caused by concurrent username or email signups
            db.session.rollback()
            flash("That username or email address is already in use.", "error")
            return render_template("signup.html")

        flash("Account created successfully!")

        return redirect(url_for("auth.signup"))

    return render_template("signup.html")


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["LOGIN_RATE_LIMIT"],
    methods=["POST"],
    deduct_when=lambda response: response.status_code == 200,
)
def login():

    next_url = _safe_next_url(request.values.get("next"))

    if request.method == "POST":

        # Retrieve the login credentials entered by the user
        username = request.form["username"].strip()
        password = request.form["password"]

        # Ensure both login fields have been completed
        if not username or not password:

            flash("Please fill in all fields.")

            return render_template("login.html", next_url=next_url)

        # Look up the account associated with the entered username
        user = User.query.filter_by(username=username).first()

        if not user:

            flash("Invalid username or password.")

            return render_template("login.html", next_url=next_url)

        # Verify that the entered password matches the stored password hash
        if not check_password_hash(user.password_hash, password):

            flash("Invalid username or password.")

            return render_template("login.html", next_url=next_url)

        # Store the user's ID to keep them logged in
        session["user_id"] = user.user_id

        flash("Logged in successfully!")

        return redirect(next_url or url_for("home"))

    return render_template("login.html", next_url=next_url)


@auth.errorhandler(429)
def login_rate_limit_exceeded(_error):
    """Display a helpful response when login attempts exceed the limit."""

    flash("Too many login attempts. Please wait before trying again.", "error")
    return render_template("errors/429.html"), 429


@auth.route("/logout", methods=["POST"])
def logout():

    # Remove the current user's session information
    session.pop("user_id", None)

    flash("Logged out successfully!")

    return redirect(url_for("auth.login"))
