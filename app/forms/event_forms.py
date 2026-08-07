from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import (
    DataRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)


# Collect and validate the information required to create a new event
class EventForm(FlaskForm):
    """Form for creating a new event."""

    # Collect the event's basic details
    title = StringField(
        "Event Title", validators=[DataRequired(), Length(min=3, max=100)]
    )

    description = TextAreaField(
        "Description", validators=[Optional(), Length(max=1000)]
    )

    # Collect the event's location information
    venue_name = StringField("Venue Name", validators=[DataRequired(), Length(max=100)])

    address = StringField("Address", validators=[DataRequired(), Length(max=255)])

    city = StringField("City", validators=[DataRequired(), Length(max=100)])

    country = StringField("Country", validators=[DataRequired(), Length(max=100)])

    location_notes = TextAreaField(
        "Location Notes", validators=[Optional(), Length(max=1000)]
    )

    # Collect when the event will begin and end
    start_datetime = DateTimeLocalField(
        "Start Date & Time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )

    end_datetime = DateTimeLocalField(
        "End Date & Time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )

    # Allow organisers to set an attendance limit
    capacity = IntegerField(
        "Maximum Capacity", validators=[Optional(), NumberRange(min=1)]
    )

    # Allow precise event locations to be stored if available
    latitude = FloatField("Latitude", validators=[Optional()])

    longitude = FloatField("Longitude", validators=[Optional()])

    # Allow organisers to choose who can view the event
    privacy = SelectField(
        "Privacy",
        choices=[("Public", "Public"), ("Private", "Private")],
        validators=[DataRequired()],
    )

    # Keep lifecycle values explicit and validated by WTForms
    status = SelectField(
        "Status",
        choices=[
            ("Draft", "Draft"),
            ("Published", "Published"),
            ("Cancelled", "Cancelled"),
        ],
        default="Draft",
        validators=[DataRequired()],
    )

    image = FileField("Event Image")
    remove_image = BooleanField("Remove the current image")

    # Submit the completed event creation form
    submit = SubmitField("Save Event")

    # Validate relationships between multiple form fields
    def validate_end_datetime(self, field):
        """Ensure the event ends after it starts."""

        if (
            field.data is not None
            and self.start_datetime.data is not None
            and field.data <= self.start_datetime.data
        ):
            raise ValidationError(
                "The event end date and time must be after the start date and time."
            )


# Preserve the existing import used by callers and tests
CreateEventForm = EventForm
