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
demo/program     / Program@FMSS2026!
demo/finance     / Finance@FMSS2026!
demo/admin       / Admin@FMSS2026!
general_admin    / GeneralAdmin@FMSS2026!     ← Platform General Admin (approvals only)
```

Legacy alias still accepted during transition: `superadmin` / `SuperAdmin@FMSS2026!`

**Company users** sign in as `company-slug/username` (e.g. `demo/admin`).

**General Admin** uses the **General Admin** link on the login page (not the company form).
After login, open **Firm Approvals** to approve/reject registered companies.

### Professional upgrade highlights
- General Admin role (approvals + technical corrections only — no company finance)
- Project-based budgets and full project financial analysis with charts
- 10 currencies (NGN, USD, EUR, GBP, GHS, KES, ZAR, XOF, CAD, CNY)
- IFRS-oriented COA / reporting language
- Fixed Owner/General Admin console login + Registered Firms approval table
- Streamlined company registration (pending → approved by General Admin)

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
