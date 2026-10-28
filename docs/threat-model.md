# FDR Sentinel local prototype threat model

## Scope and assumptions

This threat model covers one developer-operated local prototype using a browser, FastAPI, local SQL database and private filesystem storage. It does not claim production readiness. Assume the workstation account, operating system and local dependencies are trusted; shared-host, remote-network and hostile multi-user deployment are out of scope. No real bank confirmation or fund transfer exists.

## Assets

| Asset | Examples | Main protection |
|---|---|---|
| Credentials and sessions | Demo passwords, Argon2 hashes, JWT signing key, persisted token sessions | `.env` exclusion, Argon2, short-lived tokens, session revocation, server-side authorization |
| Submitted and extracted record values | Institution, instrument, obligation and release-request fields | Pydantic validation, backend role checks, institution-scoped queries, database constraints |
| Original evidence | Uploaded PDF/image bytes, SHA-256 and storage metadata | Private local directory, generated storage names, media/size checks, authorized download, immutable new-version records |
| Decisions and accountability | Workflow, audit, verification and release-approval events | Actor derived from auth, explicit transitions and exact-role gates, append-only application-level event controls |
| Local demo state | SQLite DB, synthetic fixtures, notifications and local configuration | Git ignores, reset backup, deterministic seed, synthetic-only values |

## Threats and mitigations

| Threat | Mitigation in prototype | Remaining limitation |
|---|---|---|
| Institution user reads another institution's data by changing an ID or filter | Backend queries enforce institution scope and return not-found for inaccessible IDs; API tests exercise ID and query substitutions. | Must be retested for every new endpoint and role. Internal roles currently have broad cross-institution reads. |
| Unauthorized or wrong-role decision | Auth dependency verifies persisted session; exact role dependencies gate scrutiny, final approval and release decisions; lifecycle services reject invalid transitions. | No fine-grained case assignment or separation-of-duties policy beyond implemented role gates. |
| Credential theft or secret leakage | Argon2 password hashes, short-lived signed bearer tokens, revocable sessions; local signing key comes from environment; root `.env` ignored. | Local workstation/browser token exposure and local secret handling remain risks; no production key rotation/secret manager. |
| Malicious or misleading upload | Size/type/content checks, generated storage names, private storage, SHA-256, original preservation, exception status/audit handling. | No antivirus sandbox, remote malware scanning, or robust OCR pipeline; users should only use synthetic files. |
| Path traversal or overwrite of evidence | User filenames are metadata only; generated server-side storage key; separate upload records and checksums. | Local filesystem access remains available to the workstation owner. |
| OCR/extraction or similarity treated as proof | Extraction and system findings are provenance-labeled, explainable candidates; missing fields remain unknown; no auto-approval/release. | Human reviewers can still misinterpret outputs; UI/process training is needed before any real use. |
| Accidental or malicious changes to audit evidence | Audit/workflow/verification events have application-level update/delete guards; actions record actor and summaries. | A local DB administrator can alter files/database directly; this is not tamper-proof, cryptographically chained, or independently monitored. |
| Accidental demo reset destroys local work | Reset restricted to development + project-local file-backed SQLite, backs up the database before migration/reseed, and leaves uploaded files untouched. | User must retain/manage backups and must stop the app before resetting. PostgreSQL reset is intentionally unsupported. |
| Fake bank verification impression | Synthetic records carry labels; UI/docs state no real verification, bank connection or transfer; no external bank integration. | Demo presenter must keep synthetic label visible and not describe flags as proof. |
| Cross-origin browser request | API CORS allowlist is restricted to local Vite origins by default. | Local browser extensions/proxies and changed developer CORS settings are outside this control. |

## Safe local demo practices

- Use only synthetic records and generated documents. Do not upload real account, institution or personal data.
- Keep `.env`, local DBs/backups and `backend/data/` out of Git; never copy their contents into issue logs.
- Bind Uvicorn to `127.0.0.1`; do not expose the development server to a LAN.
- Stop the backend before database reset and retain its generated backup until the clean restart is verified.
- Treat discrepancies and duplicate/similarity findings as review leads, not allegations or authenticity decisions.
- Record an explicit authorized human approval in the demo; explain that no funds move.

## Future integration gates

Any real institution or bank integration, production use, remote deployment, OCR service, or handling of real financial/personal data requires explicit authorization plus a separate security review. That work would need deployment-specific identity and secret management, access-control review, durable and protected file storage, backup/recovery, monitoring, retention/privacy policy, operational incident handling, and integration-specific verification tests. None is implemented or implied by this local demo.
