import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    DecimalField,
    FileField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)
from wtforms.widgets import HiddenInput


# Collect and validate information when creating or editing an event
class EventForm(FlaskForm):

    # Collect the event's main details
    title = StringField(
        "Event Title",
        validators=[
            DataRequired(),
            Length(max=100),
        ],
    )

    description = TextAreaField(
        "Description",
        validators=[
            DataRequired(),
            Length(max=1000),
        ],
    )

    # Collect the event's location information
    venue_name = StringField(
        "Venue Name",
        validators=[
            DataRequired(),
            Length(max=100),
        ],
    )

    address = StringField(
        "Street Address",
        validators=[
            DataRequired(),
            Length(max=255),
        ],
    )

    postcode = StringField(
        "Postcode",
        validators=[
            DataRequired(),
            Length(max=20),
        ],
    )

    city = StringField(
        "City",
        validators=[
            DataRequired(),
            Length(max=100),
        ],
    )

    country = StringField(
        "Country",
        validators=[
            DataRequired(),
            Length(max=100),
        ],
    )

    location_notes = TextAreaField(
        "Location Notes",
        validators=[
            Optional(),
            Length(max=500),
        ],
    )

    latitude = DecimalField(
        "Latitude",
        validators=[
            Optional(),
            NumberRange(min=-90, max=90),
        ],
        places=6,
    )

    longitude = DecimalField(
        "Longitude",
        validators=[
            Optional(),
            NumberRange(min=-180, max=180),
        ],
        places=6,
    )

    # Collect the event's schedule and availability information
    start_datetime = DateTimeLocalField(
        "Start Date & Time",
        validators=[
            DataRequired(),
        ],
        format="%Y-%m-%dT%H:%M",
    )

    end_datetime = DateTimeLocalField(
        "End Date & Time",
        validators=[
            DataRequired(),
        ],
        format="%Y-%m-%dT%H:%M",
    )

    capacity = IntegerField(
        "Capacity",
        validators=[
            Optional(),
            NumberRange(min=1),
        ],
    )

    registration_deadline = DateTimeLocalField(
        "Registration Deadline",
        validators=[Optional()],
        format="%Y-%m-%dT%H:%M",
    )

    privacy = SelectField(
        "Privacy",
        choices=[
            ("Public", "Public"),
            ("Private", "Private"),
        ],
        validators=[
            DataRequired(),
        ],
    )

    invite_expires_at = DateTimeLocalField(
        "Private Link Expiry",
        validators=[Optional()],
        format="%Y-%m-%dT%H:%M",
    )

    invited_emails = TextAreaField(
        "Invited Email Addresses",
        validators=[Optional(), Length(max=4000)],
    )

    requests_open = BooleanField("Accept new attendance requests", default=True)

    status = SelectField(
        "Status",
        choices=[
            ("Draft", "Draft"),
            ("Published", "Published"),
            ("Cancelled", "Cancelled"),
        ],
        validators=[
            DataRequired(),
        ],
    )

    # Allow the organiser to upload or remove an optional event image
    image = FileField(
        "Event Image",
        validators=[
            Optional(),
            FileAllowed(
                ["jpg", "jpeg", "png", "webp"],
                "Only JPEG, PNG and WebP images are allowed.",
            ),
        ],
    )

    image_crop_x = IntegerField(
        "Horizontal image position",
        default=50,
        validators=[Optional(), NumberRange(min=0, max=100)],
        widget=HiddenInput(),
    )
    image_crop_y = IntegerField(
        "Vertical image position",
        default=50,
        validators=[Optional(), NumberRange(min=0, max=100)],
        widget=HiddenInput(),
    )

    remove_image = BooleanField("Remove current image")

    submit = SubmitField("Save Event")

    # Ensure the event ends after it begins
    def validate_end_datetime(
        self,
        field,
    ):

        if (
            self.start_datetime.data
            and field.data
            and field.data <= self.start_datetime.data
        ):

            raise ValidationError(
                "End date and time must be after the start date and time."
            )

    def validate_registration_deadline(self, field):
        if (
            field.data
            and self.start_datetime.data
            and field.data >= self.start_datetime.data
        ):
            raise ValidationError("Registration must close before the event starts.")

    def validate_invite_expires_at(self, field):
        if self.privacy.data == "Private" and not field.data:
            raise ValidationError("Private events require an invite-link expiry date.")
        if (
            field.data
            and self.end_datetime.data
            and field.data > self.end_datetime.data
        ):
            raise ValidationError(
                "The private link must expire by the end of the event."
            )

    def validate_invited_emails(self, field):
        emails = [value for value in re.split(r"[\s,;]+", field.data or "") if value]
        invalid = [
            email
            for email in emails
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ]
        if invalid:
            raise ValidationError(
                "Enter valid email addresses separated by commas or new lines."
            )
