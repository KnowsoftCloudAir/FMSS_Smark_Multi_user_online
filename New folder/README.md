# Knowsoft FMSS ERP (Web)

## Render deploy (important)

This is a **FastAPI** app (not Flask). Do **not** use `gunicorn app:app`.

### Option A — Native Python (simplest)

In Render Dashboard → your Web Service → **Settings**:

| Setting | Value |
|---------|--------|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT` |

### Option B — Docker

- Environment: **Docker**
- Dockerfile path: `./Dockerfile`
- Start command: leave empty (uses Dockerfile CMD)

### Demo logins

```
superadmin / Knowsoft@Super0160!
demo/admin / Admin@Knowsoft1!
demo/finance / Finance@Knowsoft1!
demo/program / Program@Knowsoft1!
```

Delete any old SQLite DB after schema changes so tables recreate on startup.


## Updates (bank recon & reports)

1. **Bank reconciliation** starts with *Balance as per closing bank statement* and ends with *Balance as per cashbook* (after verified ticks). Includes **bank charges**, unpresented cheques, deposits in transit.
2. **Correction requests** — finance selects staff; staff opens **Corrections**, amends the entry, and **resubmits**.
3. **Approve** on bank recon applies a **stamp** (reviewer initials + UTC date).
4. **Download PDF** then **Synchronise to internal memory** — reports listed under Reports for later viewing.
5. PDF page 1: company logo/name, report title, date, **dashboard snapshot** KPIs, then detail pages.
6. **Approved payment vouchers** PDF include organisation, logo, invoice details, approvers, and signature lines.

> The desktop script `KnowsoftFMSSeclient_smek.py` was not available on this environment; core financial PDFs (TB, ledger, variance, bank recon, assets, inventory, vendors, payments, vouchers) follow the same branded layout. Paste that file into the project if you need exact additional report layouts ported 1:1.
