# Local demo validation results

Validation date: 2026-10-25. Checks below used the existing `backend/.venv/` and `frontend/node_modules/`; no dependencies were installed. All test/demo records and credentials used for validation were synthetic. The temporary SQLite database and its backup were removed after validation.

## Commands run and actual results

### Backend and database

Commands ran from `backend/` unless noted:

| Command / action | Result |
|---|---|
| `.venv/bin/python -m pytest` | **Passed:** 72 tests, 6 dependency deprecation warnings, 6.51 seconds. |
| `.venv/bin/python -m compileall app migrations scripts` | **Passed:** application, migrations and scripts compiled. |
| `.venv/bin/alembic current` | **Passed:** `e3b4a3935b14` for the default local database. |
| `.venv/bin/alembic heads` | **Passed:** single head `ab192c82d7e1`. |
| `DATABASE_URL=sqlite:////Users/aviralprakash/Desktop/fdr-sentinel/backend/.demo_verification.sqlite APP_ENV=development JWT_SECRET_KEY=<local-test-value> .venv/bin/alembic upgrade head` | **Passed:** all migrations applied to a disposable SQLite database. Alembic emitted its known SQLite warning about a skipped implicit constraint `ALTER`. |
| `.venv/bin/python -m scripts.seed_demo` with that disposable DB | **Passed:** printed 5 institutions, 30 instruments, 5 obligations, 3 metadata-only documents, 3 mismatch fixtures and 3 release requests. |
| `.venv/bin/python -m scripts.seed_users` with `FDR_DEMO_PASSWORD` set only in the command environment | **Passed:** printed nine fictional demo account emails and roles; no password was printed. |
| `.venv/bin/python -m scripts.reset_demo` with the disposable DB | **Passed:** made a timestamped SQLite backup, reapplied migrations and seeded 5 institutions/30 instruments. The uploaded-document directory was untouched. |
| SQLAlchemy count check after reseeding demo users | **Passed:** 5 institutions, 30 instruments, 13 total users (4 loginless synthetic fixture identities plus 9 demo accounts). |
| FastAPI `TestClient` GET `/api/v1/health` against the migrated disposable DB | **Passed:** HTTP 200, `{"status":"ok","database":"connected"}`. |
| FastAPI `TestClient` POST `/api/v1/auth/login` for `institution01@fdr-sentinel.invalid` | **Passed:** HTTP 200 and an access token was returned; token/password values were not printed. |
| `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765` | **Could not start a live listener:** application startup completed, but the environment rejected socket binding with `[Errno 1] Operation not permitted`. This is a sandbox restriction, not an application startup exception. |

The seed account run happened before and after reset; reset intentionally re-creates the baseline demo dataset, after which `scripts.seed_users` recreates the nine login accounts. `.env` was not read or printed, and no value from it was copied into tracked files.

### Frontend

Commands ran from `frontend/`:

| Command | Result |
|---|---|
| `npm test` (run as part of `npm test && npm run build`) | **Passed:** 6 tests across 4 files. |
| `npm run build` | **Passed:** TypeScript check and Vite production build; 1,665 modules transformed. |

### Configuration and local files

| Check | Result |
|---|---|
| `pg_isready` | PostgreSQL client reported `/tmp:5432 - no response`; PostgreSQL validation was unavailable, so SQLite was used. |
| `git check-ignore -v backend/.demo_verification.sqlite.backup-20261024T210359Z` after ignore update | **Passed:** timestamped SQLite backups are ignored. The database and backup were then removed. |
| Review `.env.example` | **Passed:** contains only placeholder signing key and example local DB settings; no actual credentials. |
| Review `frontend/package.json` | **Passed:** documents `npm ci`, `npm run dev`, `npm test`, and `npm run build` scripts via root README. |

## What these checks establish

- Migrations, synthetic seed, demo-account seed, reset/backup, account login, and database health work against a disposable local SQLite DB.
- The FastAPI health handler returns its expected healthy JSON response in-process.
- Backend tests, frontend tests, TypeScript validation and production frontend bundling pass.
- The documented live Uvicorn bind could not be verified in this sandbox because socket binding is denied. A browser-to-live-API demonstration therefore remains unverified here.

## Known limitations and unverified areas

- No PostgreSQL server was listening locally; PostgreSQL migrations and runtime behavior were not tested.
- Fresh package installation (`python -m pip install -r backend/requirements.txt`, `npm ci`) was not repeated because the project environments/dependencies were already present.
- No browser-driven full workflow was run. Frontend verification is Vitest plus build; backend scenario coverage is API-level using isolated SQLite fixtures.
- Scanned-document OCR/Tesseract, bank verification, external identity provider, real fund movement, cloud services and LLM features are not configured or implied.
- The backend currently has no draft-field `PATCH /api/v1/fdrs/{id}` endpoint; clarification responses are recorded as comments and resubmit the case. There is no global audit-feed endpoint. Internal review roles currently have broad cross-institution read access; institution users remain tenant-scoped.
- Maturity reminders are generated by a repeat-safe local command. Date-based dashboard queries do not require it. Lifecycle status does not automatically change solely because a maturity date passes.
- SQLite emits a migration warning that some unsupported implicit-constraint `ALTER` behavior is skipped; use PostgreSQL for a more representative relational migration check when a local server is available.
