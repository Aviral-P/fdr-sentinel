# SIH PS 26265 — Acceptance Test Matrix

This matrix describes automated API-level acceptance coverage in the local synthetic prototype. Passing tests are not evidence of live bank integration, production readiness, or real-world fraud-detection accuracy.

| Acceptance area | Automated evidence | Current scope / limitation |
|---|---|---|
| Institution submission and role-based scrutiny | `test_e2e_scenarios.py` cross-role journey | API-level; no browser automation in this suite |
| Document upload, extraction and discrepancy review | Cross-role journey with synthetic text PDF and field review | Extraction is a review aid; not bank-authenticity verification |
| Repeated clarification | `test_acceptance_repeated_clarification_rounds_are_distinct_and_audited` | Checks two separate requests, prevents reuse of an answered request, and verifies timeline events |
| Renewal/replacement lineage | `test_acceptance_successor_chain_supports_multiple_generations` | Checks three generations through API and record links; UI interaction is not browser-tested |
| Release eligibility and authorized decision | Release acceptance scenario | Approval records authorization only; no transfer or actual discharge occurs |
| Maturity reminders and repeat-safe operations | Maturity/operations tests | Scheduled execution depends on the local scheduler being installed and running |
| Institution isolation | Tenant-scoped API journey | Internal reviewers retain broader cross-institution read access as documented |
| Audit trail | History and append-only ORM guard tests | ORM guard is not database-level tamper-proof storage |
| Integrity rule evaluation | `python -m scripts.integrity_evaluation` | Small, planted synthetic fixture only; no generalization claim |
| Live bank / AICTE integration | Not tested or implemented | Requires authorized external interfaces and credentials |

## Run acceptance checks

From `backend/` with the project's virtual environment activated:

```bash
python -m pytest -q tests/test_e2e_scenarios.py
python -m pytest -q
python -m scripts.integrity_evaluation
```

Record the actual command output and date in the submission evidence. Do not present fixture-only recall as production accuracy.


## Operational worklist usability update (2026-10-26)

- The submitted-case worklist exposes server-side institution, maturity-date range, and priority filters while preserving offset pagination.
- The dashboard “Open findings” metric links to the integrity findings workspace with `review_status=open`, rather than the general instrument action queue.
- The findings workspace reads review status from the URL so the dashboard destination is reflected in the selected filter.
- Frontend regression coverage verifies the worklist API filter contract and dashboard destination.

These are UI navigation and filtering improvements. They do not imply external bank verification, case assignment, or production-grade access segregation.
