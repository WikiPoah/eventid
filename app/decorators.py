from functools import wraps

from flask import session, redirect, url_for


# Restrict access to routes that require a logged in user
def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        # Redirect users to the login page if they are not authenticated
        if "user_id" not in session:

            return redirect(url_for("auth.login"))

        return view(*args, **kwargs)

    return wrapped_view