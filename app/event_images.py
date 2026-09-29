from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError


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

    try:
        with Image.open(file_storage.stream) as image:
            width, height = image.size
            if width * height > current_app.config["EVENT_IMAGE_MAX_PIXELS"]:
                return None, "The event image dimensions are too large."
            image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError):
        return None, "The uploaded file is not a valid supported image."
    finally:
        file_storage.stream.seek(0)

    return detected_extension, None


def save_event_image(file_storage, _extension, crop_x=50, crop_y=50):
    """Normalize, crop and save an image without retaining uploaded metadata."""

    upload_directory = Path(current_app.config["EVENT_IMAGE_UPLOAD_FOLDER"])
    upload_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.webp"
    target = upload_directory / filename
    temporary = upload_directory / f".{uuid4().hex}.tmp"
    try:
        with Image.open(file_storage.stream) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode in {"RGBA", "LA"}:
                canvas = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A")
                canvas.paste(image.convert("RGB"), mask=alpha)
                image = canvas
            else:
                image = image.convert("RGB")

            width, height = image.size
            target_ratio = 16 / 9
            if width / height > target_ratio:
                crop_width = round(height * target_ratio)
                left = round((width - crop_width) * (crop_x / 100))
                box = (left, 0, left + crop_width, height)
            else:
                crop_height = round(width / target_ratio)
                top = round((height - crop_height) * (crop_y / 100))
                box = (0, top, width, top + crop_height)

            image = image.crop(box).resize(
                current_app.config["EVENT_IMAGE_OUTPUT_SIZE"], Image.Resampling.LANCZOS
            )
            image.save(temporary, format="WEBP", quality=85, method=6)
        temporary.chmod(0o600)
        temporary.replace(target)
    except OSError:
        # Remove a partial upload before returning control to the transaction
        for path in (temporary, target):
            if path.is_file():
                path.unlink()
        raise
    finally:
        file_storage.stream.seek(0)
    return filename


def delete_event_image(filename):
    """Remove only a generated event image within the configured directory."""

    if not filename or Path(filename).name != filename:
        return
    upload_directory = Path(current_app.config["EVENT_IMAGE_UPLOAD_FOLDER"]).resolve()
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
