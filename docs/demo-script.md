# Five-minute synthetic demo script

## Before the demo

Follow the root README to apply migrations, seed the demo records, seed development accounts, and start FastAPI and Vite. Use the locally chosen demo password. Open the UI at the Vite URL and verify `GET /api/v1/health` shows database connectivity. Keep all data fictional; seeded document entries are metadata fixtures, not bank-issued evidence.

## Walkthrough

### 0:00–0:40 — Explain the boundary

Introduce FDR Sentinel as a local prototype. Point out that the current data is synthetic, integrity findings are review aids, and the app performs no real bank verification or transfer.

### 0:40–1:20 — Institution dashboard

Sign in as `institution01@fdr-sentinel.invalid`. Show institution-scoped metrics and a maturity item. Open the FDR repository and explain the submitted values as institution-provided information.

### 1:20–2:00 — Synthetic document evidence

Open a seeded discrepancy case or upload a generated synthetic text PDF to an institution-owned draft. Show the document metadata/hash and extracted candidate fields beside declared values. Explain that the extraction candidate is not official verification. A scanned image/PDF may accurately show `ocr_required` because OCR is not configured.

### 2:00–2:50 — Scrutiny and history

Sign in as `reviewer@fdr-sentinel.invalid`. Open the prioritized queue, show the planted amount/reference finding and its supporting values, and request clarification on a permitted case. Show the workflow history entry. State explicitly that the finding is not proof of fraud.

### 2:50–3:35 — Replacement lineage

Open the synthetic renewal/replacement pair. Show the successor link and separate histories. Explain that both records and their evidence are preserved; the seed is illustrative.

### 3:35–4:20 — Release eligibility and approval

Open a release-pending case. Show a required eligibility condition that blocks the request, then explain that a blocked case cannot be approved. If demonstrating an eligible synthetic request, sign in as `approver@fdr-sentinel.invalid` and record a human approval. The result is an application decision only; no bank instruction, release or transfer occurs.

### 4:20–5:00 — Maturity, notification and audit

Show the approaching maturity in the dashboard/action queue and the in-app reminder. Sign in as `auditor@fdr-sentinel.invalid` and inspect permitted history. Explain that auditors can read but cannot change instrument state or decisions. Close by noting that no external bank, OCR, LLM, or cloud service participates.

## Demo accounts

Use the fictional `.invalid` accounts in the README and the local password entered when running `scripts.seed_users`. Do not put the local password in this document or commit it. Reset the SQLite database only with the guarded, backup-producing command in the README; re-seed accounts afterward.
