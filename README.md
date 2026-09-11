# Knowsoft FMSS ERP (Web)

Multi-company financial management: payments, COA, bank reconciliation, inventory, assets, vendors, procurement (committee → PO → payment), projects, and branded PDF reports.

## Render deploy

This is a **FastAPI** app.

### Settings

| Setting | Value |
|---------|--------|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT` |

Or use **Docker** with the included `Dockerfile`.

**Clear build cache** after large updates. Pin uses `bcrypt==4.0.1` (required for passlib).

## Demo logins (seeded on startup)

```
demo/program  / Program@Knowsoft1!
demo/finance  / Finance@Knowsoft1!
demo/admin    / Admin@Knowsoft1!
superadmin    / Knowsoft@Super0160!
```

Company users use `company-slug/username`. Login page shows the program manager demo only.

On first start (and when demo COA is empty), the app seeds chart of accounts, budgets, payments, inventory, projects, vendors, and procurement at multiple workflow stages.

## Local run

```bash
pip install -r requirements.txt
cd backend && uvicorn main:app --reload --port 8000
```

Open http://127.0.0.1:8000

## Project layout

```
backend/     FastAPI API, models, reports, seed
frontend/    SPA (index.html, app.js, styles.css)
static/      logos and uploads
```
