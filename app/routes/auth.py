from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from app.database.db import db
from app.models.user import User

# Create a blueprint to handle user authentication routes
auth = Blueprint("auth", __name__)


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

        # Check that the chosen username is not already in use
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:

            flash("That username is already taken.")

            return render_template("signup.html")

        # Ensure each email address can only be registered once
        existing_email = User.query.filter_by(email=email).first()

        if existing_email:

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
            password_hash=password_hash
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
def login():

    if request.method == "POST":

        # Retrieve the login credentials entered by the user
        username = request.form["username"].strip()
        password = request.form["password"]

        # Ensure both login fields have been completed
        if not username or not password:

            flash("Please fill in all fields.")

            return render_template("login.html")

        # Look up the account associated with the entered username
        user = User.query.filter_by(username=username).first()

        if not user:

            flash("Invalid username or password.")

            return render_template("login.html")

        # Verify that the entered password matches the stored password hash
        if not check_password_hash(user.password_hash, password):

            flash("Invalid username or password.")

            return render_template("login.html")

        # Store the user's ID to keep them logged in
        session["user_id"] = user.user_id

        flash("Logged in successfully!")

        return redirect(url_for("home"))

    return render_template("login.html")


@auth.route("/logout", methods=["POST"])
def logout():

    # Remove the current user's session information
    session.pop("user_id", None)

    flash("Logged out successfully!")

    return redirect(url_for("auth.login"))
