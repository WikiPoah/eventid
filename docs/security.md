# Security operations

## Local configuration

EventID requires `SECRET_KEY` at startup and does not use a fallback. For local
development, copy `.env.example` to `.env` and generate a new random value. The
`.env` file and SQLite databases are ignored by Git.

Production must inject `SECRET_KEY` through its secret manager or environment;
the development `.env` file should not be deployed.

## Response policy

Every response receives `nosniff`, clickjacking protection, a strict-origin
referrer policy, a restrictive permissions policy, and a self-hosted Content
Security Policy. Production HTTPS responses also receive HSTS. The CSP allows
only same-origin scripts, styles, fonts, forms, and images (plus data images),
so inline scripts and unreviewed third-party assets are not permitted.

Uploaded images are authorized through their owning event, validated by file
signature and size, stored under generated names, and served with `nosniff` and
cache metadata. Logs must never include secrets, passwords, sessions, uploaded
contents, or attendee exports.

## Authentication destinations and recommendations

Public discovery never grants access to private, Draft, or Cancelled events.
State-changing and personal routes remain authenticated and CSRF-protected.
Post-login destinations accept only local absolute paths; external URLs,
protocol-relative paths, schemes, hosts, and backslash variants are discarded.

Recommendations are rendered only for an authenticated user and calculated
from that user’s existing attendance records at request time. They expose no
attendee names, private events, raw scores, stored profile, or sensitive
inference. Popularity is aggregate-only and used as a fallback signal.

## Compromised-secret history cleanup

Rotating the key is mandatory even if history is rewritten. History rewriting
only reduces future exposure; it cannot make a previously published value safe.

Perform cleanup from fresh mirror clones after all current work has been
committed and reviewed. Run these commands from a directory outside the working
repository:

```powershell
git clone --mirror https://github.com/WikiPoah/eventid.git eventid-backup.git
git clone --mirror https://github.com/WikiPoah/eventid.git eventid-clean.git
Set-Location eventid-clean.git
git for-each-ref --format='%(refname)' refs/heads refs/tags
```

Record the branch and tag names printed by `git for-each-ref`. The rewrite must
preserve these names, including `main`, `develop`, and every existing release
tag. Their target commit hashes will change because rewriting a commit also
rewrites every descendant commit.

Create `secret-replacements.txt` locally with the exact compromised value on
the left side. Do not commit or paste that value into an issue or terminal
transcript:

```text
literal:<COMPROMISED_SECRET>==>REMOVED_COMPROMISED_FLASK_SECRET
```

Then install and run `git-filter-repo`:

```powershell
python -m pip install git-filter-repo
git filter-repo --replace-text secret-replacements.txt
$replacementLine = Get-Content -LiteralPath secret-replacements.txt
$compromisedSecret = ($replacementLine -replace '^literal:', '') -replace '==>.*$', ''
git log "-S$compromisedSecret" --all --oneline
git for-each-ref --format='%(refname)' refs/heads refs/tags
git fsck --full --no-reflogs --unreachable
Remove-Item -LiteralPath secret-replacements.txt
Remove-Variable replacementLine, compromisedSecret
git remote add origin https://github.com/WikiPoah/eventid.git
git push --force --mirror origin
```

`git filter-repo` normally removes the original remote as a safety measure. If
`git remote -v` shows that `origin` still exists, use `git remote set-url
origin https://github.com/WikiPoah/eventid.git` instead of `git remote add`.

The `git log` verification must produce no output, and the second ref listing
must contain the same branch and tag names recorded before the rewrite. Run an
additional secret scanner against the rewritten mirror before pushing. The
force push is destructive: coordinate a maintenance window, preserve the
untouched mirror backup, protect active work, and require every collaborator to
re-clone. Old clones can reintroduce rewritten history and should not be used
for normal pushes afterward.

Afterward, review GitHub secret-scanning alerts, repository security alerts,
Actions secrets, deployment environments, and logs. Revoke/rotate the Flask
secret everywhere even after the rewrite, invalidate active sessions, and
replace any other credential reported by scanning.

## Attendance concurrency

SQLite has no PostgreSQL-style row lock. EventID therefore starts `BEGIN
IMMEDIATE` before reading an event's attendance count and inserting a row. This
serializes SQLite writers and makes the capacity decision while the write lock
is held. A busy timeout lets a competing request wait, then re-check the count.

For PostgreSQL, the same route locks the event row with `SELECT FOR UPDATE`
inside the transaction. This serializes registrations for one event without
serializing unrelated event registrations. Production should use PostgreSQL
when write concurrency or availability requirements exceed SQLite's single-
writer design.
