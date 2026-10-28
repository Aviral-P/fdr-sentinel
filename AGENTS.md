# FDR Sentinel — Project Instructions

FDR Sentinel is an AICTE Security Deposit/FDR Management and Intelligence Portal. It is a local-development prototype being built under a strict 48-hour deadline. Deployment is out of scope.

## Product scope

Build a reliable end-to-end workflow supporting:

1. Institution-wise and instrument-wise FDR records.
2. Secure document upload, storage, and retrieval.
3. Role-based access for institution users, scrutiny officers, approving authorities, and auditors.
4. Controlled submission, scrutiny, clarification, and decision workflow.
5. Validity and maturity monitoring, renewal, and replacement tracking.
6. Release/refund requests with eligibility checks and explicit authorized approval.
7. Audit trail for important record changes and decisions.
8. Document text extraction and declared-versus-extracted field comparison.
9. Explainable discrepancy flags and cross-record duplicate detection.
10. Dashboards, actionable queues, reports, and synthetic demo data.

Prioritize complete, reliable workflows over superficial feature count. Keep the application straightforward to run locally from a fresh terminal.

## Technology and runtime constraints

- Frontend: React, TypeScript, Vite, Tailwind CSS, shadcn/ui, and Lucide icons.
- Backend: Python, FastAPI, and Pydantic.
- Python environment: `backend/.venv/`. Install and run every Python package through this environment; never install packages globally.
- ORM: SQLAlchemy 2.x. Migrations: Alembic.
- Database: PostgreSQL for local development, or SQLite temporarily if PostgreSQL is unavailable.
- Backend tests: pytest. Frontend tests: Vitest and React Testing Library where practical.
- Document extraction: PyMuPDF for text-based PDFs. Tesseract OCR may be added for scanned documents.
- API communication: REST/JSON. Keep frontend and backend contracts consistent.
- Local development only. Do not add cloud deployment, external bank integration, or production infrastructure.

Use explicit dependency versions or compatible version ranges, and update dependency files when dependencies change. Keep secrets in environment variables and provide `.env.example`. Never commit `.env`, credentials, tokens, or uploaded documents.

## Non-negotiable engineering and safety rules

1. Inspect existing files before modifying them. Never overwrite existing work blindly.
2. Build incrementally; do not generate the entire application in one step.
3. Keep business logic in backend services, not React components.
4. Validate important state transitions and permissions on the backend.
5. Enforce institution-level data isolation in backend queries.
6. Record audit events for important changes and decisions.
7. Preserve original uploaded documents. Never silently overwrite evidence.
8. OCR results and similarity flags are leads for human review, never proof of fraud or authenticity.
9. Never automatically approve, release, or transfer funds based on AI output. Release/refund requires eligibility checks and explicit authorized human approval.
10. Distinguish institution-submitted information, extracted information, system-generated findings, and independently verified information in data models and UI.
11. Use fictional synthetic data for demonstrations. Never present simulated bank verification as real bank confirmation.
12. Do not introduce real external integrations without explicit authorization.
13. Do not add unnecessary technologies such as microservices, graph databases, message brokers, or vector databases.

## Workflow for every milestone

### Before implementation

- Inspect the relevant project files and current state.
- Summarize the implementation plan.
- Identify dependencies and risks.
- Define concrete acceptance criteria.

### After implementation

- Run relevant tests and syntax/build checks.
- Fix failures before declaring the milestone complete.
- Report changed files, exact commands run, actual results, and remaining limitations.
- Do not proceed to an unrelated milestone until the current milestone meets its acceptance criteria.
- Do not claim a feature works unless it has been implemented and tested.

## Development commands and conventions

- Run Python tooling through `backend/.venv/bin/` (for example, `backend/.venv/bin/python -m pytest`).
- Keep backend configuration and environment setup documented for a fresh local terminal.
- Prefer small, reviewable changes with clear API schemas and service boundaries.
- Add or update tests for backend authorization, institution scoping, workflow transitions, audit events, extraction/comparison behavior, and frontend API-facing behavior as those areas are implemented.
- Do not commit generated uploads, local databases, environment files, or other user data.
