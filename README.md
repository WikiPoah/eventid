# EventID

EventID is a full-stack event discovery and management web application built with Flask.

It allows users to discover events, create an account, attend events, save favourites, and manage events they organise through a dedicated organiser dashboard.

The project was originally developed as a database-focused application and has since grown into a broader full-stack portfolio project covering authentication, relational data modelling, validation, concurrency, event management, responsive UI design, testing, and secure application structure.

> **Current release:** `v0.9.1 – Recruiter Preview`
> EventID is actively being polished ahead of its first stable `v1.0.0` release.

---

## Overview

EventID supports two main use cases:

### Attendees

Users can:

- create an account and log in using either username or email
- browse public events
- search and filter events
- view detailed event information
- register attendance
- save favourite events
- view events they are attending

### Organisers

Organisers can:

- create events
- edit existing events
- manage event status and visibility
- upload event images
- set event capacity
- manage venue and location information
- view attendee information
- export attendee data as CSV
- manage their events from a dedicated dashboard

---

## Key Features

### Authentication

- user registration
- secure password hashing
- login with username or email
- automatic login after registration
- protected authentication routes for already logged-in users
- session-based authentication

### Event Management

- create, edit, publish, cancel and delete events
- organiser-only management controls
- public/private event visibility
- draft, published and cancelled event states
- event capacity limits
- event image uploads
- event categories
- detailed venue and location information

### Attendance

- users can register for events
- duplicate registrations are prevented
- organisers cannot attend their own events
- event capacity is enforced
- last-place registration is protected against concurrent requests

### Discovery

- browse events
- search and filtering
- category-based discovery
- homepage event carousels
- event detail pages
- personalised application areas for attendees and organisers

### Organiser Dashboard

- overview of organised events
- event statistics
- upcoming event management
- attendee CSV export
- clear empty states and management actions

### User Interface

The current frontend includes redesigned:

- navigation
- authentication pages
- event creation and editing forms
- organiser dashboard
- My Events page
- homepage
- footer
- responsive layouts

The interface is intentionally designed to be clean and restrained, inspired by modern developer and SaaS products rather than highly decorative UI patterns.

---

## Technology Stack

### Backend

- Python
- Flask
- Flask-WTF
- SQLAlchemy
- Flask-Migrate
- WTForms
- Jinja2

### Database

- SQLite for local development
- relational SQLAlchemy models
- Alembic migrations through Flask-Migrate

### Frontend

- HTML
- CSS
- Jinja templates
- JavaScript

### Development

- Git
- GitHub
- pytest
- environment-based configuration

---

## Project Structure

A simplified view of the project is shown below:

```text
eventid/
├── app/
│   ├── database/
│   │   ├── db.py
│   │   └── seed.py
│   ├── forms/
│   ├── models/
│   ├── routes/
│   │   ├── auth.py
│   │   └── events.py
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── uploads/
│   └── templates/
├── migrations/
├── tests/
├── .env.example
├── .gitignore
├── main.py
├── requirements.txt
└── README.md
```

The exact contents may evolve while the project approaches `v1.0.0`.

---

# Running EventID Locally

## 1. Prerequisites

Install:

- Python 3.11 or newer
- Git
- pip

You can confirm Python is available with:

```bash
python --version
```

On some systems the command may be:

```bash
python3 --version
```

---

## 2. Clone the Repository

```bash
git clone https://github.com/WikiPoah/eventid.git
cd eventid
```

---

## 3. Create a Virtual Environment

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Once activated, your terminal should normally show `(.venv)`.

---

## 4. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Configure Environment Variables

Copy the example environment file.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Open `.env` and replace any placeholder values with local development values.

At minimum, the application requires a Flask secret key.

Example:

```env
SECRET_KEY=replace-this-with-a-random-development-secret
```

Never commit the real `.env` file to Git.

---

## 6. Prepare the Database

Apply the existing database migrations:

```bash
flask --app main db upgrade
```

If Flask cannot find the application automatically, make sure the virtual environment is active and that you are running the command from the project root.

The development database uses SQLite.

---

## 7. Run the Application

Start EventID with:

```bash
python main.py
```

If you prefer Flask's development runner, you can also use:

```bash
flask --app main run
```

Then open the local address shown in the terminal, normally:

```text
http://127.0.0.1:5000
```

---

## 8. Run the Test Suite

From the project root:

```bash
python -m pytest
```

The project includes automated tests covering core application behaviour including authentication, event management, attendance and related business rules.

---

# Database Design

EventID uses a relational data model.

Core entities include:

### User

Stores account and profile information.

Examples include:

- username
- email
- password hash
- profile details
- organiser status

### Event

Stores event information including:

- title
- description
- start and end date/time
- venue
- street address
- postcode
- city
- country
- optional latitude and longitude
- event status
- privacy
- capacity
- organiser

### Category

Represents event categories.

Events and categories use a many-to-many relationship.

### Attendance

Connects users to events they are attending.

A composite key prevents duplicate attendance records.

---

# Selected Engineering Decisions

## Concurrency-Safe Capacity Handling

Capacity-limited events require more than a simple count followed by an insert.

EventID includes protection against two users simultaneously claiming the final available place.

The local SQLite implementation uses transaction locking appropriate to SQLite, while the design also considers row-level locking for databases such as PostgreSQL.

---

## Secure Event Ownership

Editing, deletion and attendee exports are restricted to the organiser who owns the event.

Server-side checks are used rather than relying only on hidden interface controls.

---

## Application Configuration

Sensitive configuration such as the Flask secret key is stored outside the source code using environment variables.

The real `.env` file is excluded from version control and `.env.example` documents the expected configuration.

---

## Validation

Forms are validated server-side using Flask-WTF and WTForms.

Registration and event forms preserve user input when validation fails so users do not have to re-enter valid information.

---

# Current Development Status

EventID is currently at:

## `v0.9.1 – Recruiter Preview`

This version is intended to be presentable for portfolio and recruiter review while final frontend work continues.

The core application and backend functionality are already in place.

Remaining work before `v1.0.0` is primarily refinement rather than a fundamental application rewrite.

### Planned before v1.0.0

- final homepage carousel refinement
- Event Details visual polish
- Browse Events consistency pass
- full responsive QA
- accessibility review
- final UI consistency pass
- Calendar completion

The Calendar feature is currently intentionally marked as **Coming soon** instead of exposing an unfinished experience.

---

# Release Approach

EventID uses semantic versioning.

Recent milestones have included:

- authentication
- event models and relationships
- event creation
- browsing and details
- search and categories
- attendance and favourites
- organiser functionality
- event management
- frontend and portfolio polish

The first stable release will be tagged:

```text
v1.0.0
```

only after the remaining visual, responsive and accessibility work has been completed.

---

# What I Learned

Building EventID has involved working across more than just basic CRUD functionality.

Key areas include:

- relational database modelling
- authentication and authorisation
- secure server-side validation
- Flask application organisation
- database migrations
- transaction handling
- concurrency concerns
- file uploads
- CSV exports
- responsive interface design
- automated testing
- Git branching and semantic versioning
- iterative frontend refinement

---

# Roadmap

### v0.9.1 – Recruiter Preview

Current recruiter-ready preview release.

### v1.0.0 – First Stable Release

Planned focus:

- final UI consistency
- accessibility
- responsive QA
- Event Details redesign
- Browse Events polish
- carousel refinement
- Calendar completion or stable release treatment

Future versions may expand discovery, recommendations, organiser tooling and deployment capabilities.

---

## Notes for Reviewers

EventID is under active development.

The `v0.9.1` release represents a deliberately stable recruiter preview of the application before the remaining frontend and accessibility work is completed for `v1.0.0`.

Feedback is welcome.
