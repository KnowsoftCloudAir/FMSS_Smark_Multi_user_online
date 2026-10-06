# Knowsoft FMSS standard ERP

Multi-company finance ERP with chart of accounts, payments, inventory, assets, vendors, procurement, multi-currency, and owner approval of new companies.

## Run

```
pip install -r requirements.txt
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000

## Owner backend

The public login page does not show a password. Owner approval is a separate console.

- Username: `owner`
- Password: `Owner@FMSS2026!` (kept out of the sign-in page)
- Pending demo firm: Harbour Trust Foundation (`harbour-trust`). Approve it from Owner approvals.
- A new company stays pending until the owner approves it. Approving twice does not create a second licence.

## Demo company

- Firm slug: `demo`
- Users: `demo/admin`, `demo/finance`, `demo/program`
- Currencies seeded: NGN, USD, GBP, EUR, GHS, with rates into NGN
- Tasks: USD workshop fee and GBP audit fee, plus the Harbour approval task

## Tasks

A task can only move draft → submitted → assigned → in progress → complete → closed. Failed tasks retry back to in progress. An illegal step is rejected and the database is rolled back.
