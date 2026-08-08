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

    remove_image = BooleanField(
        "Remove current image"
    )

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