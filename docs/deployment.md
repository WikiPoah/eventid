# Production deployment and recovery

## Selected platform

Render is the reference deployment because its Blueprint supports a Python web service, managed PostgreSQL, pre-deploy migration command, environment secrets, persistent disk, health checks, and GitHub-based main-branch deployment in one reviewable file.

## Deploy

1. In Render, create a Blueprint from this GitHub repository and select `render.yaml`.
2. Review region and paid `starter` web, database, and disk plans before creation.
3. Confirm `main` is the deployment branch and keep the generated `SECRET_KEY` secret.
4. Replace `RATELIMIT_STORAGE_URI=memory://` with a private Redis URL before scaling beyond one process/instance.
5. Deploy; Render installs runtime packages, upgrades the database, seeds the event categories, starts Waitress, and checks `/health`.

`DATABASE_URL` accepts `postgres://` and `postgresql://` provider formats and normalizes them for psycopg 3. Secure cookies and proxy handling are enabled by `FLASK_ENV=production`.

Production startup requires both `SECRET_KEY` and `DATABASE_URL`; it must not silently create a local SQLite database. PostgreSQL connections use connection health checks before reuse. Local development and explicit test configurations continue to support SQLite.

## Dedicated demo instance

Demo accounts use publicly known credentials. Seeding is disabled outside development/tests unless `ALLOW_DEMO_SEED=true` is explicitly set. Use that option only on a separate demo instance without real user data. After deployment, run `flask --app main:app seed-demo-data` in the service's runtime Shell, then disable the option again. Run this at runtime because the persistent image disk is unavailable to Render's pre-deploy command. Repeating the seed does not duplicate the demo records.

Configure `RESEND_API_KEY` and `MAIL_FROM` before demonstrating password recovery or email verification. Without a mail provider, ordinary signup/login work, but those email-based flows cannot deliver messages. The single-process blueprint uses an in-memory rate limiter; counters reset on restart. Shared Redis storage is required if deploying multiple workers/instances.

## Images

The blueprint mounts `/var/data/eventid`; uploads live below it and survive deploys. A single instance can use this disk. Render disks do not provide shared multi-instance storage, so horizontal scaling requires adapting the image backend to S3-compatible object storage. Back up the disk separately from PostgreSQL.

## Database backup and restore

Use Render PostgreSQL recovery/export features or `pg_dump` with a short-lived connection string. Before a risky migration, take a database backup and verify its timestamp. Restore into a separate database first, validate it, update `DATABASE_URL` during a maintenance window, then run `flask --app main:app db upgrade`. Never place connection strings in shell history, documentation, or Git.

For local SQLite, stop the app and copy `instance/eventid.db` plus `instance/event_images`. Restore both together, then run migrations. Preserve environment secrets independently; database backups do not contain the Flask secret.

Test downgrade/upgrade compatibility on a disposable copy, never directly on the only production database. The health endpoint reports only `{"status":"ok"}` or `{"status":"unhealthy"}`.
