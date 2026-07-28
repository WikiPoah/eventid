from app.database.db import db


# Store the relationship between events and their categories
class EventCategory(db.Model):

    __tablename__ = "event_categories"

    # Link each record to an event and a category
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("events.event_id"),
        primary_key=True
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.category_id"),
        primary_key=True
    )

    # Allow navigation between events and their categories
    event = db.relationship(
        "Event",
        back_populates="categories"
    )

    category = db.relationship(
        "Category",
        back_populates="events"
    )

    def __repr__(self):

        # Return a readable representation of the event-category relationship
        return (
            f"<EventCategory "
            f"Event {self.event_id} "
            f"Category {self.category_id}>"
        )