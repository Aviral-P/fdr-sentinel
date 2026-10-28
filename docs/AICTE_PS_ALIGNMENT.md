# AICTE PS 26265 alignment and acceptance checklist

This checklist maps the official Security Deposit/FDR Management Portal requirements to the local FDR Sentinel prototype. “Implemented” means source-level capability exists; demonstrate it with the test/demo path before claiming production readiness. The application uses synthetic demo records and does not connect to a bank or AICTE production system.

| # | Official capability | Existing implementation | Acceptance evidence / remaining gap |
|---:|---|---|---|
| 1 | Centralized repository | Institution and FDR models, register and institution views, filtered list API | Demonstrate institution scoping, search, create/read/update and dashboard totals against DB records. |
| 2 | Digital document management | Private storage, content validation, checksum, downloads, labeled PDF text extraction | Optional Tesseract OCR is now available via `LOCAL_OCR_ENABLED=true`; install Tesseract locally. Test PDF and image uploads and failure states. |
| 3 | Verification/discrepancy detection | Extracted candidates remain separate from declared values; integrity rules and review queue | Demonstrate clean, missing-field, mismatch, duplicate and near-duplicate synthetic cases. Bank confirmation is not implemented; do not claim authenticity verification. |
| 4 | Validity/maturity tracking | Dashboard date calculations, repeat-safe reminder generator, and scheduled approved→matured status advancement with audit events | Configure the macOS LaunchAgent with `backend/scripts/install_macos_reminder_schedule.sh`; it runs daily at 09:00 local time. Verify status advancement and a reminder against synthetic maturity dates. |
| 5 | Renewal/replacement monitoring | Successor records and predecessor/successor linkage; approval-controlled supersession | Demonstrate successor creation and approval, confirming the prior record remains in history. |
| 6 | Release/refund workflow | Release requests, eligibility evaluation, authorized decision and disposition | Demonstrate eligible and ineligible cases, institution scope, and that approval records authorization only (no money movement). |
| 7 | Alerts/escalation | In-app maturity reminders plus deduplicated overdue action escalation notifications for institution users and internal scrutiny/approval/admin roles; escalation events are audited | Run the daily operations job twice and confirm the second run creates no duplicates; inspect notification recipient, reason, related instrument and audit event. External email/SMS delivery is not configured. |
| 8 | Dashboard/reports | Summary, queue and JSON/CSV reports with filters | Cross-check dashboard totals and report rows against DB and test active/expiring/matured/released/pending cases. |
| 9 | Audit trail/access control | Append-only audit/workflow rows, per-instrument history, role guards; new global `/api/v1/audit/events` feed | Verify role denial for institution users on global feed, internal role access, institution isolation, and that sensitive before/after payloads are not returned. |
| 10 | Integration/data security | JWT sessions with placeholder-secret rejection, Argon2 password hashes, private files, checksum validation, audit events, configurable CORS | Local prototype only. Production requires security review, backup/retention policy, institution identity integration, and formally authorized bank/AICTE interfaces. |

## Suggested 12-hour sprint order

1. Run backend and frontend tests; preserve a known-good checkpoint.
2. Exercise the complete workflow with synthetic data: draft → submit → scrutiny/clarification → resubmit → authorized decision.
3. Exercise document upload, extracted-vs-declared mismatch review, integrity scan, and audit feed.
4. Exercise successor/renewal and release request/decision.
5. Install and verify local reminder scheduling; verify report filters and dashboard counts.
6. Run the full regression suite and record exact results.

## Truthful limitations to disclose

- All seeded institutions, instruments and bank names are fictional.
- Text extraction/OCR and integrity rules create review candidates, not proof of fraud or authenticity.
- No live bank verification, AICTE system integration, email/SMS delivery or money transfer is implemented.
- The local prototype is not production-hardened.
