from app.database.db import db


class EventCategory(db.Model):
    """Explicit event/category association with pair-level uniqueness."""

    __tablename__ = "event_categories"

    event_id = db.Column(db.Integer, db.ForeignKey("events.event_id"), primary_key=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.category_id"), primary_key=True
    )

    event = db.relationship("Event", back_populates="event_categories")
    category = db.relationship("Category", back_populates="event_categories")

    def __repr__(self):
        return (
            f"<EventCategory " f"Event {self.event_id} " f"Category {self.category_id}>"
        )
