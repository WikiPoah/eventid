import resend
from flask import current_app
from resend.exceptions import ResendError


def send_email(recipient, subject, text):
    """Deliver a transactional email through Resend's supported Python SDK."""

    if current_app.testing:
        current_app.extensions.setdefault("mail_outbox", []).append(
            {"to": recipient, "subject": subject, "text": text}
        )
        return True

    api_key = current_app.config.get("RESEND_API_KEY")
    sender = current_app.config.get("MAIL_FROM")
    if not api_key or not sender:
        current_app.logger.warning(
            "Email not sent because RESEND_API_KEY or MAIL_FROM is not configured."
        )
        return False

    resend.api_key = api_key
    try:
        result = resend.Emails.send(
            {
                "from": sender,
                "to": [recipient],
                "subject": subject,
                "text": text,
            }
        )
    except (ResendError, RuntimeError) as error:
        current_app.logger.error("Transactional email delivery failed: %s", error)
        return False
    return bool(result.get("id"))
