# SIH PS 26265 — prototype readiness and acceptance evidence

This document describes what the current local prototype can demonstrate. It is not a claim of production certification or integration with AICTE/banks.

## Requirement-to-demo map

| PS requirement | Prototype capability | Demonstration / evidence | Boundary to disclose |
|---|---|---|---|
| Institution-wise and instrument-wise repository | Institution records, FDR register, scoped list/detail and edit endpoints | Log in as two institution users; confirm each sees only its own records; search and filter the register | Seed records are fictional |
| Digital document upload, storage, retrieval and review | Private file storage, upload validation, checksum, authenticated retrieval, PDF text extraction, optional local OCR | Upload a synthetic text PDF; inspect checksum, extraction method/status and declared-vs-extracted candidates | Seeded metadata-only document fixtures are now labelled and disabled when no original file exists |
| Verification and discrepancy handling | Deterministic integrity rules, extracted-vs-declared comparisons, required-check queue, human review | Run integrity scan against the synthetic dataset; review a mismatch and inspect the audit trail | No bank API or external source credentials are configured; rule findings are leads, not proof of authenticity/fraud |
| Validity, maturity and advance reminders | Date-based dashboard metrics, configurable reminder windows, repeat-safe reminders, and scheduled approved→matured status advancement with audit events | Run `cd backend && .venv/bin/python -m scripts.generate_reminders`; confirm expired approved instruments transition to `matured`, audit events are written, and reminders are created | Local reminders require the OS user session/scheduler; no external email/SMS delivery |
| Renewal/replacement history | Linked successor drafts and approval-controlled predecessor supersession | Create a successor, approve it with an authorized role, navigate both records and inspect history | Approval does not imply release of funds |
| Release/refund workflow | Request creation, eligibility evaluation, authorized decision and recorded disposition | Submit eligible and ineligible synthetic requests; decide as approving authority; inspect release report | No payment rail, bank instruction, or actual transfer |
| Alerts and escalation | In-app maturity reminders, deduplicated overdue-action escalations routed to institution users and internal scrutiny/approval/admin roles, audited escalation events, pending scrutiny worklist and prioritized action queue | Run `cd backend && .venv/bin/python -m scripts.generate_reminders` twice against synthetic overdue cases; confirm first-run notifications/audit events and no duplicates on the second run | In-app only; no email/SMS gateway; institution role assignments are broad and should be policy-configured before production |
| Dashboard and reports | DB-backed summary, filters for maturity dates/lifecycle/priority, operational queues and CSV reports | Change filters and compare dashboard values to exported rows | Current figures are based on local database state |
| Audit trail and access control | Role guards, institution isolation, workflow history, redacted global audit feed and audit summaries for edits | Check institution cross-access denial; inspect events as internal reviewer/auditor; confirm institution users cannot use global feed | ORM-level append-only controls are not a tamper-proof external ledger; no fine-grained case assignment |
| Integration and data security | Short-lived revocable JWT sessions, Argon2 password hashes, secret-placeholder rejection, private files, checksum, CORS allowlist | Inspect configuration and run tests; confirm `.env` is not in the deliverable ZIP | Local prototype only; formal authorization, external integrations, production secrets, backup/retention and security review remain prerequisites |

## Synthetic integrity evaluation

Run from the repository root:

```bash
cd backend
.venv/bin/python -m scripts.integrity_evaluation
```

The committed synthetic fixture reports 7/7 planted discrepancy cases detected, 3/3 planted duplicate pairs detected, and zero false-positive candidates linked to two clean controls. These are fixture-level counts, not real-world accuracy, a fraud probability, or evidence of authenticity.

## Local verification commands

```bash
cd backend
.venv/bin/python -m pytest -q
cd ../frontend
npm test
npm run build
```

The backend regression suite was rerun after the maturity automation change: **83 passed**. The frontend suite and production build passed on the earlier uploaded baseline (15 tests across 9 files); they must be rerun after applying the current frontend changes before treating this revision as fully verified.

## Measurable outcome protocol for a judging demo

Do not claim improvements without a baseline. Use the same synthetic cases in both a manual spreadsheet workflow and FDR Sentinel, then record:

- **Detection coverage:** known planted discrepancies surfaced / known planted discrepancies.
- **Duplicate review coverage:** known planted duplicate pairs surfaced / planted pairs.
- **Review turnaround:** elapsed minutes from submission to recorded scrutiny outcome for each case.
- **Reminder timeliness:** due reminders generated before maturity / reminders expected by configured windows.
- **Manual effort:** number of operator steps or minutes required to locate a case, inspect evidence, produce a report and record a decision.
- **Visibility:** time required to answer how many active, expiring, matured, pending and released instruments exist from the same dataset.

Report raw counts, dates, dataset size and method. Do not generalize the synthetic evaluation to live institutions or real bank documents.
