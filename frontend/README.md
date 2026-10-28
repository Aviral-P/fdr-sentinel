# FDR Sentinel frontend

The React, TypeScript, Vite and Tailwind frontend uses the local FastAPI API. It reads no seeded data from local arrays; authenticated dashboard, institution, FDR, workflow, document, notification and report views call the backend.

## Local setup

In one terminal, configure and run the backend using the commands in [`../backend/README.md`](../backend/README.md). Apply migrations and seed the fictional demo records and development accounts before signing in. The seeded accounts accept the local password provided to the backend development seed script; no credentials are embedded in this app.

In a second terminal, from `frontend/`:

```sh
cp .env.example .env.local
npm install
npm run dev
```

Open the Vite URL printed by the command (normally `http://127.0.0.1:5173`). `VITE_API_BASE_URL` is the backend origin, defaulting to `http://127.0.0.1:8000` to match the documented Uvicorn bind address. It is a public URL setting; never put secrets in frontend environment variables. The app appends `/api/v1` itself. If you already have a local `.env.local`, set its `VITE_API_BASE_URL` to this value and restart Vite so it reloads environment settings.

Run the TypeScript/production build and UI/API-client tests from `frontend/`:

```sh
npm run build
npm test
```

The bearer token is held in `sessionStorage` for the current browser tab and cleared on a backend 401. Role-specific buttons are hidden or shown for usability; backend authorization remains authoritative. Original documents are fetched through the authenticated download endpoint for preview. Extraction and integrity findings are presented as review leads, never authenticity or fraud determinations.

Audit history is currently available through the backend's per-instrument `GET /api/v1/fdrs/{fdr_id}/history` endpoint. The Audit History page selects an instrument and renders its workflow/audit events; a global cross-institution audit feed is not present in the current API contract.
