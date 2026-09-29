"""Account forms, signed email links and revocable browser sessions."""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.database.db import db
from app.decorators import login_required
from app.email_delivery import send_email
from app.models.security import SecurityEvent, UserSession
from app.models.user import User
from app.rate_limit import limiter

# Create a blueprint to handle user authentication routes

auth = Blueprint("auth", __name__)

COMMON_PASSWORDS = {
    "123456789012",
    "letmeinplease",
    "password1234",
    "qwertyuiop12",
    "welcome12345",
}

IDENTITY_CHANGE_COOLDOWN = timedelta(days=7)


def _client_ip():
    return (request.remote_addr or "")[:64] or None


def _session_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _device_label():
    value = request.user_agent.string or "Unknown browser"
    for name in ("Chrome", "Safari", "Firefox", "Edge"):
        if name in value:
            return f"{name} · {value[:220]}"
    return value[:255]


def _record_security_event(user, event_type, description):
    db.session.add(
        SecurityEvent(
            user_id=user.user_id,
            event_type=event_type,
            description=description,
            ip_address=_client_ip(),
        )
    )


def _start_user_session(user):
    """Track a browser token by hash; the caller commits with the login change."""

    token = secrets.token_urlsafe(32)
    session["session_token"] = token
    db.session.add(
        UserSession(
            token_hash=_session_hash(token),
            user_id=user.user_id,
            user_agent=_device_label(),
            ip_address=_client_ip(),
        )
    )
    return token


def _ensure_user_session(user):
    token = session.get("session_token")
    if token:
        return _session_hash(token)
    _start_user_session(user)
    _record_security_event(user, "session_started", "Current session secured")
    db.session.commit()
    return _session_hash(session["session_token"])


def _account_token(user, purpose):
    """Bind email links to identity/version and separate purposes with salts.

    Changing email or auth_version invalidates prior links even before expiry;
    a verification token cannot be substituted for a password-reset token.
    """

    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"]).dumps(
        {
            "user_id": user.user_id,
            "email": user.email,
            "auth_version": user.auth_version,
        },
        salt=f"eventid-{purpose}",
    )


def _token_user(token, purpose, max_age):
    try:
        data = URLSafeTimedSerializer(current_app.config["SECRET_KEY"]).loads(
            token, salt=f"eventid-{purpose}", max_age=max_age
        )
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get("user_id"))
    if (
        user is None
        or user.email != data.get("email")
        or user.auth_version != data.get("auth_version")
    ):
        return None
    return user


def _verification_email(user):
    link = url_for(
        "auth.verify_email",
        token=_account_token(user, "verify-email"),
        _external=True,
    )
    return (
        user.email,
        "Verify your eventid email",
        f"Hello {user.first_name},\n\nVerify your email address:\n{link}\n\n"
        "This link expires in 24 hours. If you did not create this account, "
        "you can ignore this email.",
    )


def _send_verification_email(user):
    return send_email(*_verification_email(user))


def _cooldown_error(label, changed_at, now):
    """Return the next allowed identity-change date when still cooling down."""

    if changed_at is None:
        return None
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=UTC)
    available_at = changed_at + IDENTITY_CHANGE_COOLDOWN
    if now >= available_at:
        return None
    return (
        f"You can change your {label} again on "
        f"{available_at.strftime('%d %B %Y at %H:%M')}."
    )


def _password_error(password, username, email):
    """Return a clear error for passwords that are unsafe or expensive to hash."""

    minimum = current_app.config["PASSWORD_MIN_LENGTH"]
    maximum = current_app.config["PASSWORD_MAX_LENGTH"]
    if len(password) < minimum:
        return f"Your password must be at least {minimum} characters long."
    if len(password) > maximum:
        return f"Your password must be no more than {maximum} characters long."
    normalized = password.casefold()
    if normalized in COMMON_PASSWORDS or len(set(normalized)) < 4:
        return "Choose a less predictable password."
    email_name = email.partition("@")[0].casefold()
    if username.casefold() in normalized or (
        len(email_name) >= 3 and email_name in normalized
    ):
        return "Your password should not contain your username or email name."
    return None


def _safe_next_url(candidate):
    """Preserve local return paths without enabling an open redirect.

    Browsers can interpret protocol-relative URLs or backslashes as hosts, so
    a leading slash alone is insufficient. Keep queries for private invitations.
    """

    if not candidate:
        return None

    parsed = urlsplit(candidate)

    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None

    if parsed.path.startswith("//") or "\\" in parsed.path:
        return None

    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


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
    """Return only non-sensitive values that may be repopulated after an error."""

    return {
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "email": email,
    }


@auth.route("/signup", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["SIGNUP_RATE_LIMIT"],
    methods=["POST"],
)
def signup():
    """Create an account and preserve only a validated local return journey."""

    next_url = _safe_next_url(request.values.get("next"))

    if "user_id" in session:

        return redirect(url_for("home"))

    form_values = _signup_form_values()

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = _normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        form_values = _signup_form_values(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
        )

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
                next_url=next_url,
            )

        if password != confirm_password:

            flash(
                "Please make sure your passwords match.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
                next_url=next_url,
            )

        password_error = _password_error(password, username, email)
        if password_error:
            flash(password_error, "error")
            return render_template(
                "signup.html",
                form_values=form_values,
                next_url=next_url,
            )

        if not 3 <= len(username) <= 20:

            flash(
                "Your username must be between 3 and 20 characters.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
                next_url=next_url,
            )

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

        if any(row.username == username for row in existing_credentials):

            flash(
                "That username is already taken.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
                next_url=next_url,
            )

        if any(row.email == email for row in existing_credentials):

            flash(
                "An account with this email already exists.",
                "error",
            )

            return render_template(
                "signup.html",
                form_values=form_values,
                next_url=next_url,
            )

        password_hash = generate_password_hash(password)

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
            password_hash=password_hash,
        )

        db.session.add(new_user)

        try:

            # Flush first so the generated user ID is available before commit

            db.session.flush()

            new_user_id = new_user.user_id
            new_user_first_name = new_user.first_name
            new_user_auth_version = new_user.auth_version
            verification_email = _verification_email(new_user)
            new_session_token = _start_user_session(new_user)
            _record_security_event(new_user, "account_created", "Account created")

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
                next_url=next_url,
            )

        send_email(*verification_email)

        session.clear()
        session.permanent = True
        session["user_id"] = new_user_id
        session["auth_version"] = new_user_auth_version
        session["session_token"] = new_session_token

        flash(
            f"Welcome to eventid, {new_user_first_name}!",
            "success",
        )

        return redirect(next_url or url_for("home"))

    return render_template(
        "signup.html",
        form_values=form_values,
        next_url=next_url,
    )


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["LOGIN_RATE_LIMIT"],
    methods=["POST"],
)
def login():
    """Authenticate and replace pre-login state with a tracked session."""

    if "user_id" in session:

        return redirect(url_for("home"))

    next_url = _safe_next_url(request.values.get("next"))

    if request.method == "POST":
        identifier = (
            request.form.get("identifier") or request.form.get("username") or ""
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        normalized_identifier = identifier.lower()

        if not identifier or not password:

            flash(
                "Please fill in all fields.",
                "error",
            )

            return render_template(
                "login.html",
                next_url=next_url,
                identifier=identifier,
            )

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
                identifier=identifier,
            )

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
                identifier=identifier,
            )

        # Discard pre-login state so authenticated identity cannot inherit an
        # attacker-controlled session; the sanitized return URL was saved above.

        session.clear()
        session.permanent = True
        session["user_id"] = user.user_id
        session["auth_version"] = user.auth_version
        _start_user_session(user)
        _record_security_event(user, "login", "Successful login")
        db.session.commit()

        flash(
            f"Welcome back, {user.first_name}!",
            "success",
        )

        return redirect(next_url or url_for("home"))

    return render_template("login.html", next_url=next_url, identifier="")


@auth.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["ACCOUNT_ACTION_RATE_LIMIT"], methods=["POST"]
)
def forgot_password():
    """Request a short-lived password reset link without exposing accounts."""

    email = ""
    if request.method == "POST":
        email = _normalize_email(request.form.get("email", ""))
        user = db.session.scalar(select(User).where(User.email == email))
        if user is not None:
            link = url_for(
                "auth.reset_password",
                token=_account_token(user, "reset-password"),
                _external=True,
            )
            send_email(
                user.email,
                "Reset your eventid password",
                f"Hello {user.first_name},\n\nReset your password:\n{link}\n\n"
                "This link expires in one hour. If you did not request this, "
                "you can ignore this email.",
            )
        flash(
            "If an account uses that email, a password reset link is on its way.",
            "success",
        )
        return redirect(url_for("auth.forgot_password"))
    return render_template("forgot_password.html", email=email)


@auth.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["ACCOUNT_ACTION_RATE_LIMIT"], methods=["POST"]
)
def reset_password(token):
    """Replace a password using a valid, expiring, single-use link."""

    user = _token_user(
        token, "reset-password", current_app.config["PASSWORD_RESET_MAX_AGE"]
    )
    if user is None:
        flash("That password reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")
        if password != confirmation:
            flash("The new passwords do not match.", "error")
        else:
            password_error = _password_error(password, user.username, user.email)
            if password_error:
                flash(password_error, "error")
            elif check_password_hash(user.password_hash, password):
                flash("Choose a password you have not already been using.", "error")
            else:
                user.password_hash = generate_password_hash(password)
                user.auth_version += 1
                now = datetime.now(UTC)
                db.session.query(UserSession).filter_by(user_id=user.user_id).update(
                    {"revoked_at": now}
                )
                _record_security_event(
                    user, "password_reset", "Password reset using an emailed link"
                )
                db.session.commit()
                send_email(
                    user.email,
                    "Your eventid password was reset",
                    "Your eventid password was reset. If this was not you, contact "
                    "support and secure your email account immediately.",
                )
                session.clear()
                flash("Your password has been reset. You can now log in.", "success")
                return redirect(url_for("auth.login"))
    return render_template("reset_password.html", token=token)


@auth.get("/verify-email/<token>")
def verify_email(token):
    """Confirm that the user controls their current email address."""

    user = _token_user(
        token, "verify-email", current_app.config["EMAIL_VERIFICATION_MAX_AGE"]
    )
    if user is None:
        flash("That verification link is invalid or has expired.", "error")
        return redirect(url_for("auth.settings" if g.user else "auth.login"))
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        db.session.commit()
    flash("Your email address is verified.", "success")
    return redirect(url_for("auth.settings" if g.user else "auth.login"))


@auth.post("/resend-verification")
@limiter.limit(lambda: "3 per hour")
@login_required
def resend_verification():
    """Send a replacement verification link to the signed-in user."""

    if g.user.email_verified_at is not None:
        flash("Your email address is already verified.", "success")
    elif _send_verification_email(g.user):
        flash("A new verification link has been sent.", "success")
    else:
        flash(
            "We could not send that email right now. Please try again later.", "error"
        )
    return redirect(url_for("auth.settings"))


@auth.errorhandler(429)
def login_rate_limit_exceeded(_error):
    """Render the account-specific response when an auth limit is exceeded."""

    flash(
        "Too many login attempts. Please wait before trying again.",
        "error",
    )

    return (
        render_template(
            "errors/429.html",
        ),
        429,
    )


@auth.route("/logout", methods=["POST"])
def logout():
    """Revoke the tracked browser session before clearing its signed cookie."""

    token = session.get("session_token")
    if g.user is not None and token:
        tracked = db.session.scalar(
            select(UserSession).where(UserSession.token_hash == _session_hash(token))
        )
        if tracked:
            tracked.revoked_at = datetime.now(UTC)
            _record_security_event(g.user, "logout", "Signed out of a session")
            db.session.commit()
    session.clear()

    flash(
        "Logged out successfully!",
        "success",
    )

    return redirect(url_for("auth.login"))


@auth.route("/profile", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["ACCOUNT_ACTION_RATE_LIMIT"], methods=["POST"]
)
@login_required
def profile():
    """Display and update the current user's public account details."""

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = _normalize_email(request.form.get("email", ""))
        bio = request.form.get("bio", "").strip()
        city = request.form.get("city", "").strip()
        country = request.form.get("country", "").strip()
        now = datetime.now(UTC)
        previous_email = g.user.email
        username_changed = username != g.user.username
        email_changed = email != g.user.email

        errors = []
        if not first_name or not last_name or not username or not email:
            errors.append("First name, last name, username, and email are required.")
        if len(first_name) > 50 or len(last_name) > 50:
            errors.append("Names must be 50 characters or fewer.")
        if not re.fullmatch(r"[a-z0-9_.-]{3,20}", username):
            errors.append(
                "Username must be 3–20 characters using letters, numbers, dots, hyphens, or underscores."
            )
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 255:
            errors.append("Enter a valid email address.")
        if len(bio) > 500:
            errors.append("Your bio must be 500 characters or fewer.")
        if len(city) > 100 or len(country) > 100:
            errors.append("City and country must be 100 characters or fewer.")
        if username_changed:
            cooldown_error = _cooldown_error(
                "username", g.user.username_changed_at, now
            )
            if cooldown_error:
                errors.append(cooldown_error)
        if email_changed:
            cooldown_error = _cooldown_error("email", g.user.email_changed_at, now)
            if cooldown_error:
                errors.append(cooldown_error)

        duplicate = db.session.scalar(
            select(User.user_id).where(
                User.user_id != g.user.user_id,
                or_(User.username == username, User.email == email),
            )
        )
        if duplicate is not None:
            errors.append("That username or email address is already in use.")

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            g.user.first_name = first_name
            g.user.last_name = last_name
            g.user.username = username
            g.user.email = email
            g.user.bio = bio or None
            g.user.city = city or None
            g.user.country = country or None
            if username_changed:
                g.user.username_changed_at = now
            if email_changed:
                g.user.email_changed_at = now
                g.user.email_verified_at = None
                _record_security_event(
                    g.user, "email_changed", f"Email changed to {email}"
                )
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That username or email address is already in use.", "error")
            else:
                if email_changed:
                    _send_verification_email(g.user)
                    send_email(
                        previous_email,
                        "Your eventid email address changed",
                        f"Your eventid email was changed to {email}. If this was "
                        "not you, reset your password immediately.",
                    )
                flash("Profile updated successfully.", "success")
                return redirect(url_for("auth.profile"))

    return render_template("profile.html")


@auth.route("/settings", methods=["GET", "POST"])
@limiter.limit(
    lambda: current_app.config["ACCOUNT_ACTION_RATE_LIMIT"], methods=["POST"]
)
@login_required
def settings():
    """Display security settings and securely change the current password."""

    current_session_hash = _ensure_user_session(g.user)

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(g.user.password_hash, current_password):
            flash("Your current password is incorrect.", "error")
        elif new_password != confirm_password:
            flash("The new passwords do not match.", "error")
        elif check_password_hash(g.user.password_hash, new_password):
            flash("Choose a password you have not already been using.", "error")
        else:
            password_error = _password_error(
                new_password, g.user.username, g.user.email
            )
            if password_error:
                flash(password_error, "error")
            else:
                g.user.password_hash = generate_password_hash(new_password)
                g.user.auth_version += 1
                now = datetime.now(UTC)
                db.session.query(UserSession).filter_by(user_id=g.user.user_id).update(
                    {"revoked_at": now}
                )
                _record_security_event(
                    g.user, "password_changed", "Password changed in Settings"
                )
                db.session.commit()
                user_id = g.user.user_id
                auth_version = g.user.auth_version
                session.clear()
                session.permanent = True
                session["user_id"] = user_id
                session["auth_version"] = auth_version
                _start_user_session(g.user)
                db.session.commit()
                send_email(
                    g.user.email,
                    "Your eventid password changed",
                    "Your eventid password was changed and other sessions were "
                    "signed out. If this was not you, reset your password immediately.",
                )
                flash(
                    "Password changed. Other signed-in sessions have been logged out.",
                    "success",
                )
                return redirect(url_for("auth.settings"))

    active_sessions = db.session.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == g.user.user_id,
            UserSession.revoked_at.is_(None),
        )
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    security_events = db.session.scalars(
        select(SecurityEvent)
        .where(SecurityEvent.user_id == g.user.user_id)
        .order_by(SecurityEvent.created_at.desc())
        .limit(12)
    ).all()
    return render_template(
        "settings.html",
        active_sessions=active_sessions,
        security_events=security_events,
        current_session_hash=current_session_hash,
    )


@auth.post("/settings/sessions/<int:session_id>/revoke")
@limiter.limit(lambda: current_app.config["ACCOUNT_ACTION_RATE_LIMIT"])
@login_required
def revoke_session(session_id):
    tracked = db.first_or_404(
        select(UserSession).where(
            UserSession.session_id == session_id,
            UserSession.user_id == g.user.user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    current_hash = _session_hash(session.get("session_token", ""))
    if tracked.token_hash == current_hash:
        flash("Use Log Out to end your current session.", "warning")
        return redirect(url_for("auth.settings"))
    tracked.revoked_at = datetime.now(UTC)
    _record_security_event(g.user, "session_revoked", "Another session was revoked")
    db.session.commit()
    flash("That session has been logged out.", "success")
    return redirect(url_for("auth.settings"))


@auth.post("/settings/sessions/revoke-others")
@limiter.limit(lambda: current_app.config["ACCOUNT_ACTION_RATE_LIMIT"])
@login_required
def revoke_other_sessions():
    current_hash = _ensure_user_session(g.user)
    now = datetime.now(UTC)
    count = (
        db.session.query(UserSession)
        .filter(
            UserSession.user_id == g.user.user_id,
            UserSession.revoked_at.is_(None),
            UserSession.token_hash != current_hash,
        )
        .update({"revoked_at": now}, synchronize_session=False)
    )
    _record_security_event(
        g.user, "sessions_revoked", f"Logged out {count} other session(s)"
    )
    db.session.commit()
    flash(f"Logged out {count} other session(s).", "success")
    return redirect(url_for("auth.settings"))
