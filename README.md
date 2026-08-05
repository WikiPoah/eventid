# EventID

## Development demo data

After applying migrations, populate an existing development database with:

```powershell
python -m flask --app main:app seed-demo-data
```

The command creates clearly fictional users, events, categories, and attendance
records. It is safe to run repeatedly and does not delete or overwrite existing
data. It is intended only for local development and demonstrations.

Demo organiser: `demo_organiser`

Demo attendee: `demo_attendee`

Development-only password: `EventID-demo-2026`
