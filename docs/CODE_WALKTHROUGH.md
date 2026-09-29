# EventID interview code map

Use this as a source-reading guide, not a script to memorise. Trace an actual
request and explain the invariants before discussing libraries. The README is
for trying the application; this document explains how its implementation fits.

## Start with one request

`main.py:create_app()` selects configuration, normalizes the database URL, applies
explicit test overrides, binds extensions and registers the `auth` and `events`
blueprints. Its `load_logged_in_user()` hook resolves identity into `g.user`
and rejects invalidated sessions before a route runs. Routes then validate
input/access, query or commit through SQLAlchemy, and render Jinja or return
JSON. The response hook adds security headers. JavaScript enhances existing
forms; it does not replace server authorization.

A useful example is POST `/events/<id>/attend`: check identity → lock event →
validate visibility/lifecycle/deadline/ownership → reject duplicate/full →
insert attendance → commit → redirect with feedback. Compare this with owner
approval: it promotes Pending to Going under the same event lock.

## File Map

Paths below are relative to the repository root.

| File/module | Responsibility | Important concepts | Understand before an interview |
| --- | --- | --- | --- |
| [main.py](../main.py) | Application factory, request hooks, response headers, errors, health and CLI commands | Extension/blueprint setup, tracked-session validation, production proxy handling | Why settings are resolved before extensions and why authorization still happens in routes |
| [app/config.py](../app/config.py) | Local, test and production defaults | Environment boundaries, PostgreSQL URL normalization, SQLite engine options | Which values production requires and why explicit test overrides win |
| [app/database/db.py](../app/database/db.py), [app/rate_limit.py](../app/rate_limit.py) | Unbound SQLAlchemy/Migrate/Limiter objects | Per-application initialization | Why extension objects exist outside the factory without binding global app state |
| [app/models/event.py](../app/models/event.py), [app/models/attendance.py](../app/models/attendance.py) | Event lifecycle/access data and user registration state | Query indexes, pair-level uniqueness, capacity-counting status, ticket/check-in state | Why Attendance is an explicit association model rather than a plain many-to-many table |
| [app/models/user.py](../app/models/user.py), [app/models/security.py](../app/models/security.py) | Account identity, event ownership, revocable sessions and security history | `auth_version`, hashed session tokens, profile label versus authorization | How password changes invalidate cookies and email links |
| [app/models/category.py](../app/models/category.py), [app/models/event_category.py](../app/models/event_category.py), [app/models/favourite.py](../app/models/favourite.py) | Category and saved-event associations | Composite primary keys and view-only convenience relationships | Which constraints prevent duplicate associations |
| [app/routes/auth.py](../app/routes/auth.py) | Signup/login, profile/settings, email flows and session revocation | Password hashing/policy, safe redirects, purpose-separated signed tokens | Trace login and password reset through cookie/session invalidation |
| [app/routes/events.py](../app/routes/events.py) | Discovery, visibility, management, registration, private decisions, calendar, tickets/check-in and exports | Server authorization, lifecycle rules, capacity lock, token validation, ICS/CSV escaping | Trace one public registration and one private approval from request to commit |
| [app/decorators.py](../app/decorators.py), [app/forms/event_forms.py](../app/forms/event_forms.py) | Authentication redirect and event input contract | Local return destinations and cross-field date/invitation validation | Why route authorization cannot be replaced by form or template checks |
| [app/event_images.py](../app/event_images.py) | Validate, crop and persist event images | Byte/pixel limits, generated WebP names, atomic replace and cleanup | Which checks distrust the filename and how database/file failures are handled |
| [app/email_delivery.py](../app/email_delivery.py) | Optional transactional email adapter | Test outbox and graceful missing-provider behavior | Which account flows still work when Resend is absent |
| [app/discovery.py](../app/discovery.py), [app/recommendations.py](../app/recommendations.py) | Public homepage groups and personalized ranking | Bounded query set, aggregate popularity, deterministic tie-breaks | Why this is a small heuristic rather than an ML claim |
| [app/database/seed.py](../app/database/seed.py) | Default categories and fictional demo data | Environment guard, stable demo identities, repeatable refresh behavior | What re-seeding preserves and why it is unsafe on a real-user service |
| [app/templates](../app/templates) | Base navigation/feedback, reusable event UI and page-specific states | Server-rendered authorization state, POST fallbacks and accessible controls | Which interactions still work without JavaScript |
| [app/static/js/script.js](../app/static/js/script.js) | Progressive form, navigation, image, reveal and carousel behavior | Data attributes, CSRF-carrying `FormData`, focus/motion/history handling | Why JavaScript enhances rather than owns application state |
| [app/static/css](../app/static/css) | Tokens, shared components, page modules and responsive rules | Explicit import order, focus states, motion preference and mobile overflow | How the cascade is organized without a build framework |
| [migrations](../migrations) | Ordered schema evolution | Single revision chain, data backfills and SQLite batch operations | Why a model edit alone cannot safely update deployed databases |
| [tests/conftest.py](../tests/conftest.py), [tests/test_demo_journeys.py](../tests/test_demo_journeys.py) | Isolated fixtures and realistic attendee/organiser flows | Temporary databases/uploads, real forms, CSRF, authentication and persisted transitions | What these tests prove beyond a route returning HTTP 200 |
| [tests/test_attendance.py](../tests/test_attendance.py), [tests/test_production_v100.py](../tests/test_production_v100.py), [tests/test_migrations.py](../tests/test_migrations.py) | Capacity races, production configuration and schema verification | Competing requests, URL normalization, migration drift | Which production claims also received PostgreSQL verification outside CI |
| [tests](../tests) | Focused route, security, image, calendar, email and UI regression coverage | Authorization and state-transition assertions | What is covered and why browser/PostgreSQL checks remain separate |
| [.github/workflows/ci.yml](../.github/workflows/ci.yml), [pyproject.toml](../pyproject.toml) | Automated quality gates and tool policy | Python 3.12, Black, Ruff, coverage floor, migration and hygiene checks | What a green pull request does and does not establish |
| [render.yaml](../render.yaml), [docs/deployment.md](deployment.md) | Reference Render/PostgreSQL deployment and acceptance procedure | Pre-deploy migrations, Waitress, health check, disk and memory-limiter limits | Which checks still require a real hosted environment |

## Data and authentication

`User` owns `Event` records. `Attendance(user_id, event_id)` is an association
with registration status, opaque ticket token and check-in timestamp; its
composite primary key forbids duplicates. `EventCategory` connects events and
categories, and `Favourite` connects saved events and users with similar pair
keys. View-only convenience relationships preserve explicit association records
and their extra state. Event deletion uses ORM cascades for related records.
`UserSession` stores revocable browser-token hashes; `SecurityEvent` stores the
account activity shown in Settings.

`User.is_organiser` is a profile label, not an administrative role gate. Any
signed-in user can create an event; management authorization compares its
`organiser_id` with `g.user.user_id`. Hiding a button is never the access check.

Passwords use Werkzeug hashing. Successful authentication clears pre-login
session state and issues a signed Flask cookie containing identity,
`auth_version` and a random session token. The database stores the token's
SHA-256 hash rather than the raw token. A password change/reset increments
`auth_version` and revokes tracked sessions; Settings creates a replacement
session for the current browser after a password change. Individual revocation
is checked on the next request. Legacy/test identity-only sessions are still
accepted when the authentication version matches; normal current login creates
a tracked token. `last_seen_at` is initialized, not refreshed on every request.

`_account_token()` binds signed, expiring email links to user ID, current email
and authentication version. Different salts separate reset and verification
purposes. Password reset increments the version, making that link unusable
again. Email verification records a timestamp but is not a signup/registration
gate. `send_email()` captures a test outbox in tests and returns failure without
blocking ordinary signup if no provider is configured.

Email reset/verification links are cryptographically signed and timed. Private
invitation and ticket tokens use a different design: they are high-entropy,
opaque random values stored in the database, not self-contained signed tokens.
Invitation possession grants only the access checked by the private-event flow;
ticket routes also require the attendee or owning organiser identity.

## Registration, privacy and capacity

Events have Draft/Published/Cancelled lifecycle and Public/Private visibility.
`_can_view_event()` applies visibility to details, images, maps and calendar
exports. Owners can see their events in every lifecycle state. Public discovery
excludes private, draft, cancelled and ended events. Cancellation remains
visible to existing registrants so the event does not silently disappear.

Public registration creates Going. Private invitation access creates permission
to view/request, not a confirmed seat. `event_details()` checks token equality,
expiry, optional email allowlist and revocation, then stores the current invite
token in the session and redirects to a URL without the invitation query.
Registration creates Pending; owner approval changes it to Going and enables
ticket access. Decline changes Pending to Declined. Revocation clears check-in
and sets Revoked; restoration returns to Pending so capacity is rechecked on
approval. Existing non-revoked requests retain visibility without a live link.
Rotating an invitation invalidates link-only access, not existing attendance.

Only Going counts toward capacity. Public registration and private approval
both use `_locked_event()` **before counting**, holding the lock until
commit/rollback. Without that lock two requests could both see the final place
and both claim it. PostgreSQL locks the event row with `SELECT FOR UPDATE` and
refreshes cached ORM values. SQLite first ends the lookup transaction and uses
`BEGIN IMMEDIATE`, serializing writers for the database. Call the helper before
staging other changes because its SQLite rollback would discard them.

Registration also rejects unavailable/ended events, closed requests, expired
deadlines, owner self-registration and duplicate records. Pending requests do
not reserve seats; approval can fail when capacity is reached. The lock is a
registration/approval guarantee, not a claim that every possible event edit is
serialized. Capacity reduction is validated against confirmed attendance in
the edit form, without adopting that registration lock.

## Tickets, check-in, calendar and saved events

A random ticket token is allocated on attendance insertion, including Pending.
`_confirmed_attendance_or_404()` restricts ticket/QR retrieval to the current
user's Going record. QR generation encodes the owner's check-in URL and token;
the token alone does not grant check-in authority. The organiser must be signed
in and own that event. GET verifies/displays the attendee; a CSRF-protected POST
records check-in. Repeated sequential check-ins retain the existing timestamp,
and Undo clears it. Cancelled events reject check-in. This is not an in-app
camera scanner or a general concurrent-request exactly-once guarantee.

`calendar()` outer-joins the current user's confirmed attendance with ownership,
so owners see drafts and confirmed attendees see cancellations; unrelated events
are excluded. Events appear on their start date. ICS generation escapes event
text and converts naive stored times using the configured `EVENT_TIMEZONE`;
Google/Outlook links use provider-specific timestamp formats. The application
has one configured event timezone, not a separate timezone per venue. On mobile
the seven-column grid intentionally scrolls inside the calendar shell.

`toggle_favourite()` inserts/deletes a user/event pair for public Published or
Cancelled events. Its JSON response updates matching heart buttons; standard
POST/redirect remains the fallback. It is a toggle, not an idempotent set API.
`recommended_events()` ranks at most 40 eligible public candidates using category
and city overlap from Going attendance, aggregate popularity and deterministic
time/ID tie-breaks. This is a bounded heuristic, not ML or a personalized model.
Typo-tolerant search similarly matches filtered candidates in Python before
pagination: adequate for the demo, not a search-engine scalability claim.

## Security and frontend decisions

- Flask-WTF CSRF protects form mutations, including fetch requests carrying
  `FormData`. Email verification is the explicit signed-link GET exception.
- The response CSP permits same-origin scripts/styles and data images, with a
  Google Maps frame exception. Native `<progress>` avoids inline width styles.
- `_safe_next_url()` rejects external/protocol-relative/backslash destinations
  while preserving invitation queries for the signup/login return journey.
- Owner checks protect edit/delete/status/approval/export/check-in. Ticket
  retrieval binds identity and confirmed status; images reuse visibility checks.
- Image validation distrusts filenames, bounds bytes/pixels and normalizes to
  generated WebP names. A temporary file is atomically renamed; database failures
  remove new orphan files, and old files are deleted only after a successful edit.
- CSV formula-prefix handling and ICS escaping prevent user text from acquiring
  unintended spreadsheet/calendar structure.
- Rate limits use client addresses; production trusts exactly one forwarding
  proxy. That configuration assumes the service is behind the intended proxy.
  Secure/HttpOnly/SameSite cookies and HSTS support the HTTPS deployment.

The JS uses server-rendered forms/data attributes and server-returned action
URLs. Native mobile filter disclosure remains usable without JS. Private action
responses rebuild controls and counts; they do not bypass server authorization.
Carousel rotation moves existing slides rather than cloning IDs/forms, and
scrolls the viewport instead of competing with reveal transforms. Reduced-motion
and history-restoration paths keep content visible. Image crop sliders update
hidden percentages; Pillow performs the authoritative validation/crop.

CSS navigation: `base` = tokens/reset/focus/motion; `components` = shared
buttons/panels/feedback; `events` = cards/details/private tools/tickets/check-in;
`forms` = controls/discovery filters/crop; `landing` = homepage/carousels;
`navigation`/`footer` = chrome; `dashboard` = page shells/metrics;
`calendar` = month grid; `responsive` = shared breakpoints; `auth` = account
screens and final overrides. Existing section headings/selectors provide entry
points; the import order matters. No build framework or CSS reorganisation is
needed to explain this structure.

## Schema, configuration, demo and verification

The twelve Alembic revisions form one chain ending at `c91e4a7b2f18`.
`migrations/env.py` gets engine/metadata from the Flask application rather than a
second independently configured database. Batch operations support SQLite table
changes alongside PostgreSQL. Important transitions: postcode is added nullable,
backfilled and made required; ticket tokens are backfilled per existing row
before adding NOT NULL/uniqueness; category renaming preserves category identity.
Historical/generated migration formatting is intentionally preserved. Destructive
downgrades, especially category deletion, belong on disposable copies/backups.

`database_url()` chooses psycopg 3 for provider PostgreSQL URLs at factory time.
Explicit test overrides win; SQLite is the local fallback, and production fails
without `SECRET_KEY`/`DATABASE_URL`. PostgreSQL uses `pool_pre_ping`. SQLite uses
a busy timeout so a second writer can wait for the capacity lock.

Demo seeding rejects unapproved environments before writes because the passwords
are public. It protects reserved account identities, preserves existing demo
IDs/tokens, refreshes selected dates/images and creates missing registrations/
favourites. It does not reset every owner edit and creates no pending requests;
create one through the invitation journey. Local images/database are ignored.

Most pytest tests isolate SQLite/upload directories and bypass CSRF/login only
where testing a focused route invariant. `test_demo_journeys.py` uses real forms,
CSRF, authentication, tokens and persisted state. Its nested context prevents the
fixture's outer context from reusing Flask-WTF token caches after login resets.
`test_attendance.py` exercises competing final-seat requests; `test_migrations.py`
upgrades fresh/repeated schemas and checks model drift. Tests also cover privacy,
account email/session state, images, exports, calendar and query bounds. Names
usually explain intent better than extra comments. Two management test modules
currently duplicate cases; they were preserved rather than weakened/removed.

CI runs Python 3.12 formatting, Ruff, pytest/85% coverage, app import/routes,
migrations and tracked-file hygiene. Local final verification used Python 3.13;
Chromium browser journeys and PostgreSQL 16 checks were external disposable
harnesses, not checked-in CI jobs. Six migration-engine deprecation warnings
remain. Coverage excludes `main.py`, so the percentage is not whole-repository
coverage; factory behavior is nevertheless exercised by configuration tests.

`render.yaml` defines Waitress behind Render's HTTPS proxy, PostgreSQL, one
persistent upload disk and `/health`. Pre-deploy upgrades schema/seeds categories;
demo image seeding runs in the runtime Shell when the disk is mounted. Back up
images separately from the database. Memory rate limits reset on restart and do
not span workers; multiple instances require shared limiter/image storage.
Hosted acceptance and actual email delivery remain manual checks.

For an interview, demonstrate one invariant with code and a regression test:
last-seat approval, safe signup return, revoked-session rejection or pending
request → usable ticket → check-in. Explain the local SQLite tradeoff and what
was verified on PostgreSQL without claiming a production-scale deployment.

## Questions I should be able to answer

- Why use an application factory, and when are configuration and extensions bound? See [Start with one request](#start-with-one-request) and `main.py`.
- How do public registration and private approval prevent oversubscription? What happens when two users compete for the last place? See [Registration, privacy and capacity](#registration-privacy-and-capacity) and `_locked_event()`.
- Why does PostgreSQL matter for capacity locking, and how is the SQLite behavior different? See [Registration, privacy and capacity](#registration-privacy-and-capacity).
- Which states consume capacity, and why do Pending requests not reserve seats? See `Attendance` and [Registration, privacy and capacity](#registration-privacy-and-capacity).
- How do private links, email allowlists, rotation, revocation and restoration interact? See `event_details()` and the private-attendance decision routes.
- Which tokens are signed, which are opaque bearer values, and what extra authorization protects tickets? See [Data and authentication](#data-and-authentication) and [Tickets, check-in, calendar and saved events](#tickets-check-in-calendar-and-saved-events).
- What makes sequential check-in idempotent, and what concurrent guarantee is deliberately not claimed? See [Tickets, check-in, calendar and saved events](#tickets-check-in-calendar-and-saved-events).
- How are browser sessions revoked after a password change or reset? See [Data and authentication](#data-and-authentication) and `load_logged_in_user()`.
- How are open redirects prevented while preserving an invitation return URL? See `_safe_next_url()` and `login_required`.
- What do CSRF and CSP each protect, and why does the check-in progress use native `<progress>`? See [Security and frontend decisions](#security-and-frontend-decisions).
- Why use Alembic migrations, and which revisions required data backfills? See [Schema, configuration, demo and verification](#schema-configuration-demo-and-verification).
- How does image upload processing handle untrusted content and partial failure? See `app/event_images.py` and the create/edit routes.
- How are recommendations calculated, bounded and tested? See `app/recommendations.py` and the recommendation tests.
- What does CI verify, and which browser, PostgreSQL, email and hosted checks remain outside it? See [Schema, configuration, demo and verification](#schema-configuration-demo-and-verification).
- Why is demo seeding guarded, and what does a repeated seed preserve versus refresh? See `app/database/seed.py`.
- What limits a single-instance Render deployment, and what would change for thousands of users? Shared rate-limit storage, object storage, background email work and database-backed search/pagination are the first scaling boundaries to discuss.
