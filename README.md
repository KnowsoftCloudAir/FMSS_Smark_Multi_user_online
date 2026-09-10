# Knowsoft FMSS ERP (Web) v2.2

Multi-tenant ERP with licensing, payment workflow, assets, backup/restore.

## Platform Superadmin (approves firms + annual licenses)

```
Username: superadmin
Password: Knowsoft@Super0160!
```

## Demo company (pre-approved + licensed)

```
demo/admin     Admin@Knowsoft1!
demo/finance   Finance@Knowsoft1!
demo/program   Program@Knowsoft1!
```

Password policy (all levels): min 10 chars, upper + lower + number + special character.

## Key features

- Firm registration → **pending** until superadmin approves
- Superadmin issues **annual licenses**
- Strong passwords + password reset tokens
- Backup / restore (ZIP with JSON + CSV) for company and platform
- Payment request form: budget code → expense description → approver → program → finance (must set accounts) → pay
- Asset register with photo upload; edit limited to asset_editor / finance / project_manager / company_admin
- CSV export for payments & assets
- Dashboard stats for charts

## Run

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

© 2026 Knowsoft Consulting Ltd


## Sample data (demo company)

On first startup the **demo** company is seeded with:

- 18 chart-of-account lines
- 4 budget codes (Health, Education, Ops, Capex)
- 8 expense codes linked to debit/credit accounts
- 7 fixed assets (Good / Fair / Bad / Lost)
- 7 payment requests across the workflow:
  - 2 **paid**
  - 1 **finance_approved** (ready to pay)
  - 1 **program_approved** (awaiting finance)
  - 2 **submitted** (awaiting program)
  - 1 **rejected**
- A second firm **sunrise-ngo** left in **pending** status for superadmin approval practice

Login as `demo/program` to approve submitted requests, then `demo/finance` to set accounts and pay.
