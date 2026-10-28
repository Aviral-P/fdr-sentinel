# Backend local development

The backend runs with Python from the existing `backend/.venv/` environment. From the repository root, install dependencies and configure local settings:

```sh
backend/.venv/bin/python -m pip install -r backend/requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
```

The example configuration uses SQLite so the API starts even when PostgreSQL is not installed or running. The SQLite file is created in the current working directory. For PostgreSQL, start a local PostgreSQL server, create a local database/user, then set `DATABASE_URL` in `.env`, for example:

```dotenv
DATABASE_URL=postgresql+psycopg://fdr_sentinel:replace_me@localhost:5432/fdr_sentinel
```

Run migrations and start the API from the `backend/` directory:

```sh
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

## Data model and synthetic demo seed

The initial relational schema is kept in `migrations/versions/`. For future model changes, generate a migration from the model metadata, inspect it, then apply it:

```sh
cd backend
.venv/bin/alembic revision --autogenerate -m "describe schema change"
# Inspect the generated migration in migrations/versions/ before applying it.
.venv/bin/alembic upgrade head
```

After applying migrations, load the deterministic local demonstration dataset with:

```sh
cd backend
.venv/bin/python -m scripts.seed_demo
```

The seed is idempotent and creates five fictional institutions and thirty fictional instruments. Its issuer names, document metadata, discrepancies, and workflow examples are synthetic demo records; they do not represent bank confirmations or independently verified facts. Seeded document entries are metadata fixtures and contain no binary file.

## Authentication and local demo accounts

Authentication uses Argon2 password hashes and 15-minute signed bearer tokens backed by revocable database sessions. Configure a local signing key in `.env`; generate one without putting a real secret in the repository:

```sh
backend/.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))'
```

Copy the generated value into the local, ignored `.env` as `JWT_SECRET_KEY`. To create fictional development accounts, first change to `backend/` from the repository root. Then choose a local password interactively; the hidden input is passed only through the environment (do not run `cd backend` again if already in this directory):

```sh
read -s "FDR_DEMO_PASSWORD?Enter a local demo password (12+ characters): "
echo
export FDR_DEMO_PASSWORD
.venv/bin/python -m scripts.seed_users
```

The script only runs when `APP_ENV=development` and requires a password of at least 12 characters. It prints fictional login names and roles, never passwords or password hashes. Accounts use the reserved `.invalid` domain. Institution accounts are `institution01@fdr-sentinel.invalid` through `institution05@fdr-sentinel.invalid`; internal demo accounts are `reviewer@fdr-sentinel.invalid`, `approver@fdr-sentinel.invalid`, `auditor@fdr-sentinel.invalid`, and `admin@fdr-sentinel.invalid`. Use the local password supplied through `FDR_DEMO_PASSWORD` to sign in at `POST /api/v1/auth/login`.

Authorization is enforced on the API. Institution users are scoped to their own institution; scrutiny officers, approving authorities, and auditors can read records across institutions. Admin has explicit global read access and is not implicitly a scrutiny officer or approving authority. Final decisions are restricted to `approving_authority`; scrutiny actions require `scrutiny_officer`. Logout revokes the persisted session immediately.

Authentication routes are `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, and `POST /api/v1/auth/logout`. Institution/FDR routes include `GET /api/v1/institutions`, `GET /api/v1/institutions/{id}`, `GET /api/v1/institutions/{id}/obligations`, `POST|GET /api/v1/fdrs`, `GET /api/v1/fdrs/{id}`, and `GET /api/v1/fdrs/{id}/history`. Lifecycle actions are `POST /api/v1/fdrs/{id}/submit`, `POST /api/v1/fdrs/{id}/scrutiny`, `POST /api/v1/fdrs/{id}/clarifications/{event_id}/respond`, `POST /api/v1/fdrs/{id}/decision`, and `POST /api/v1/fdrs/{id}/successors`. Release routes are `POST /api/v1/fdrs/{id}/release-requests`, `GET /api/v1/release-requests/{id}`, and `POST /api/v1/release-requests/{id}/evaluate` and `/decision`.

FDR creation always starts in `draft`; clients cannot set lifecycle or verification status. Institution users submit drafts. Scrutiny officers request clarification or record a recommendation. The institution response resubmits the case. An approving authority records a separate final decision. Renewals/replacements are draft successors linked to their predecessor, and only successor approval supersedes the predecessor. Release eligibility reads configurable rules and current record state; an approving authority must still record a decision and disposition. Even approval records authorization only: this prototype performs no bank transfer and does not mark funds as released. Every workflow action creates append-only workflow history and an audit summary. Institution users querying another tenant's ID receive not-found responses.

These are local prototype routes. Case assignment and external verification integrations are not implemented; internal review roles currently have global read access. Reusable exact-role guards for scrutiny, approving authority, auditor, and admin are in `app/api/dependencies.py`.

## Dashboard, notifications, and reports

Authenticated users can use `GET /api/v1/dashboard/summary` and `/api/v1/dashboard/queue`. Institution users are scoped to their own institution; internal review roles see cross-institution records. Both endpoints accept `institution_id`, `date_from`, `date_to` (applied to instrument maturity date), `lifecycle_status`, and `priority`. The dashboard uses these explicit rules: active excludes draft, rejected, released, and superseded; approaching maturity means an active instrument due within the largest configured reminder window; matured requiring action means maturity is before today and status is approved, matured, or release-pending; pending scrutiny is submitted or under-scrutiny; pending authorized release is a pending release request. Open finding metrics count current integrity findings in open review status. An unresolved case has an open finding, an open required verification check, or a clarification request. Actions are overdue when maturity has passed while action remains required, or an uncompleted scrutiny/clarification/release state has been unchanged for `ACTION_OVERDUE_DAYS` (default 7).

Configure comma-separated `MATURITY_REMINDER_WINDOWS_DAYS` (default `30,15,7`). Run the repeat-safe reminder command manually:

```sh
cd backend
.venv/bin/python -m scripts.generate_reminders
```

On macOS, install a daily 09:00 local-time LaunchAgent (the app backend does not need to be running; the virtual environment must exist):

```sh
backend/scripts/install_macos_reminder_schedule.sh
```

The job log is written to `backend/logs/reminder-scheduler.log`. To uninstall it, run the `launchctl bootout` command printed by the installer and remove `~/Library/LaunchAgents/com.fdrsentinel.reminders.plist`.

It creates one in-app reminder per active institution user, instrument, and configured maturity day. A database unique key prevents repeated runs from duplicating reminders. Dashboard and report queries calculate date-based cases directly and do not rely on this command or a resident scheduler. Read notifications with `GET /api/v1/notifications?unread_only=true`; mark one read with `POST /api/v1/notifications/{notification_id}/read`. Users can only access notifications addressed to their own account.

JSON report endpoints are `GET /api/v1/reports/instruments`, `/upcoming-maturities`, `/pending-verification`, and `/release-requests`; each supports pagination and institution, maturity-date, lifecycle, and priority filters. Corresponding `.csv` paths export the filtered results as CSV. CSV values beginning with spreadsheet formula characters are escaped. Reports are local operational summaries, not externally verified bank records.

Apply the notification metadata migration before using these endpoints on an existing database:

```sh
cd backend
.venv/bin/alembic upgrade head
```

## Local document upload and extraction

Private uploaded originals are stored under `DOCUMENT_STORAGE_DIR` (default `./backend/data/documents`, resolved from the repository root), outside any frontend public directory. The directory is ignored by Git and created with owner-only permissions where supported. Configure `MAX_DOCUMENT_SIZE_BYTES` to change the upload cap (default 15 MiB). Uploads accept PDF, JPEG, PNG, and WebP, validate detected content, receive generated storage names, and retain a SHA-256 checksum. Uploading another version creates another document row; existing originals are not overwritten.

Use `POST /api/v1/fdrs/{id}/documents` with multipart field `file` as the owning institution user. List metadata and extracted candidates with `GET /api/v1/fdrs/{id}/documents`; authorized institution users and internal read roles can retrieve originals through `GET /api/v1/documents/{document_id}/download`. A scrutiny officer can record a human review of an open mismatch through `POST /api/v1/documents/{document_id}/fields/{field_name}/review`. Upload, extraction, discrepancy, review and download actions are included in the FDR history. The API does not return filesystem storage names.

Text PDFs are processed using PyMuPDF and deterministic labeled-field matching. Candidate fields include bank, branch, reference, amount, issue/maturity dates, and beneficiary. Extracted values remain separate from institution-submitted FDR fields. A missing candidate is `value_status: "missing"` with `matches_declared: null`; it is not called a mismatch. Rule-based candidates do not have calibrated confidence, so confidence is null. Mismatches create explainable open verification checks for human review and do not prove fraud or authenticity.

OCR is opt-in and uses the local Tesseract CLI when enabled. On macOS, install it with `brew install tesseract`, set `LOCAL_OCR_ENABLED=true` in the ignored root `.env`, and restart the backend. The provider processes up to five PDF pages per document, has a per-page timeout, and does not write temporary image files. If disabled or unavailable, scanned PDFs and image uploads return `ocr_required`; no OCR values are fabricated. OCR candidates remain unverified and should be reviewed by an authorized official. `app/services/extraction_service.py` defines an injectable OCR provider protocol for a future local Tesseract adapter. No bank verification or external document authenticity service is connected.

## Integrity scan and scrutiny queue

`POST /api/v1/integrity/scan` runs the deterministic local rules and persists current findings. Only a scrutiny officer can run a cross-institution scan or review/dismiss a finding. Scrutiny officers, approving authorities, auditors, and admins can read `GET /api/v1/integrity/queue` and `GET /api/v1/integrity/findings`; institution users cannot see cross-institution duplicate evidence. Review a finding with `POST /api/v1/integrity/findings/{finding_id}/review` and decision `reviewed` or `dismissed`, plus resolution notes.

The scan covers exact SHA-256 file matches, normalized reference repeats, extracted-text similarity candidates, amount/beneficiary/date discrepancies, missing required documents, near maturity without a successor, replacement-lineage conflicts, and pending release requests with unresolved required checks. Similarity candidates and field mismatches are leads for human scrutiny, not fraud or authenticity determinations. Queue scores are deterministic triage points based on severity, open review status, maturity proximity and unresolved release conditions; they are not probabilities and do not approve or reject records. `RegulatoryRule` entries with code `integrity_monitoring` may set `required_document_count` and `maturity_warning_days` globally or per institution.

Reproduce the generated synthetic evaluation report with:

```sh
cd backend
.venv/bin/python -m scripts.integrity_evaluation
```

The script rebuilds a disposable in-memory SQLite dataset and writes measured fixture counts to `docs/INTEGRITY_EVALUATION.md`. It contains clean controls, known exact/reference/text duplicate pairs, and planted discrepancies; its counts describe only those synthetic cases.

After pulling these dependency changes into the existing environment, run the backend suite and apply the new migration:

```sh
cd backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m pytest
```

The health endpoint is `http://127.0.0.1:8000/api/v1/health`. It checks both the API process and database connectivity. The default CORS allowlist permits Vite at `http://localhost:5173` and `http://127.0.0.1:5173`; override it with comma-separated `CORS_ORIGINS` values.

Run backend tests and a syntax check with:

```sh
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m compileall app migrations
```

Do not commit `.env`, local database files, or uploaded documents.


## Global audit feed

Authorized internal roles can read the paginated, filterable, redacted audit metadata feed at `GET /api/v1/audit/events`. Supported filters include `institution_id`, `entity_type`, `action`, `date_from`, `date_to`, `limit`, and `offset`. Institution users are denied access to the cross-institution feed and continue to use their scoped per-instrument history. The global feed intentionally omits before/after payloads.
