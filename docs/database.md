# eventid Database Design

## Overview

This document contains the planned database structure for eventid. It describes the purpose of each table, its fields, and the relationships between tables. The design may evolve as new features are implemented throughout the project.

---

# Tables

## User

Stores account information for every registered user. Users can browse events, save favourites, join events, and become organisers.

| Field | Description |
|-------|-------------|
| user_id | Primary key |
| first_name | User's first name |
| last_name | User's last name |
| username | Unique username |
| email | Unique email address |
| password_hash | Securely hashed password |
| profile_picture | Path to user's profile picture |
| bio | Short biography |
| country | Country of residence |
| city | City of residence |
| is_organiser | Indicates whether the user can organise events |
| created_at | Account creation timestamp |

---

## Category

Stores the different event categories.

| Field | Description |
|-------|-------------|
| category_id | Primary key |
| name | Category name |
| icon | Optional icon representing the category |

Example categories:

- Music
- Sport
- Gaming
- Food
- Education
- Charity
- Networking
- Nightlife

---

## Event

Stores information about every event.

| Field | Description |
|-------|-------------|
| event_id | Primary key |
| organiser_id | User who created the event |
| category_id | Event category |
| title | Event title |
| description | Full event description |
| country | Event country |
| city | Event city |
| street | Street name |
| building_number | Building or house number |
| postcode | Postal code |
| additional_information | Extra location details |
| latitude | Latitude returned from OpenStreetMap |
| longitude | Longitude returned from OpenStreetMap |
| date | Event date |
| start_time | Start time |
| end_time | End time |
| max_attendees | Maximum number of attendees |
| visibility | Public or Private |
| approval_required | Whether organiser approval is required |
| image | Event cover image |
| created_at | Event creation timestamp |

---

## Favourite

Stores events saved by users.

| Field | Description |
|-------|-------------|
| favourite_id | Primary key |
| user_id | User who saved the event |
| event_id | Saved event |
| saved_at | Timestamp when saved |

---

## Attendance

Stores event attendance requests and accepted attendees.

| Field | Description |
|-------|-------------|
| attendance_id | Primary key |
| user_id | User joining the event |
| event_id | Joined event |
| status | Pending, Approved, Rejected or Joined |
| request_message | Optional message for private events |
| joined_at | Timestamp of request or approval |

---

# Relationships

## User → Event

One organiser can create many events.

Relationship:

One-to-Many

---

## Category → Event

One category can contain many events.

Relationship:

One-to-Many

---

## User → Favourite ← Event

Users can save many events, and events can be saved by many users.

Relationship:

Many-to-Many

Implemented using the Favourite table.

---

## User → Attendance ← Event

Users can join many events, and events can have many attendees.

Relationship:

Many-to-Many

Implemented using the Attendance table.

---

# Future Features

The current database has been designed to support future functionality without major structural changes.

Planned features include:

- User authentication
- Favourite events
- Join requests
- Public and private events
- Organiser dashboard
- Search and filtering
- Personalised event recommendations
- Interactive maps using OpenStreetMap and Leaflet
- Address autocomplete using Nominatim
- Weather forecast integration
- Nearby events based on user location

Additional tables and fields may be introduced as the project grows.