from pathlib import Path
from uuid import uuid4

from flask import current_app


def _detected_extension(content):
    """Return the supported image extension identified by its file signature."""

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "webp"
    return None


def validate_event_image(file_storage):
    """Validate an uploaded event image without trusting its original filename."""

    if file_storage is None or not file_storage.filename:
        return None, None

    supplied_extension = Path(file_storage.filename).suffix.lower().lstrip(".")
    if supplied_extension == "jpeg":
        supplied_extension = "jpg"
    allowed = {
        "jpg" if extension == "jpeg" else extension
        for extension in current_app.config["EVENT_IMAGE_EXTENSIONS"]
    }
    if supplied_extension not in allowed:
        return None, "Upload a JPEG, PNG, or WebP image."

    # Read only up to the configured limit and restore the stream for saving
    maximum = current_app.config["EVENT_IMAGE_MAX_BYTES"]
    content = file_storage.stream.read(maximum + 1)
    file_storage.stream.seek(0)
    if len(content) > maximum:
        return None, "The event image must be 4 MB or smaller."

    detected_extension = _detected_extension(content)
    if detected_extension is None or detected_extension != supplied_extension:
        return None, "The uploaded file is not a valid supported image."

    return detected_extension, None


def save_event_image(file_storage, extension):
    """Save an image under a generated filename in the instance directory."""

    upload_directory = Path(current_app.config["EVENT_IMAGE_UPLOAD_FOLDER"])
    upload_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.{extension}"
    target = upload_directory / filename
    try:
        file_storage.save(target)
    except OSError:
        # Remove a partial upload before returning control to the transaction
        if target.is_file():
            target.unlink()
        raise
    return filename


def delete_event_image(filename):
    """Remove only a generated event image within the configured directory."""

    if not filename or Path(filename).name != filename:
        return
    upload_directory = Path(
        current_app.config["EVENT_IMAGE_UPLOAD_FOLDER"]
    ).resolve()
    target = (upload_directory / filename).resolve()
    if target.parent == upload_directory and target.is_file():
        try:
            target.unlink()
        except OSError:
            # A committed database change must not be reported as failed
            current_app.logger.warning(
                "Could not remove obsolete event image %s",
                filename,
            )
