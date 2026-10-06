# Knowsoft FMSS ERP — Professional Upgrade Guide
## From "child's play" to production-grade multi-company finance

**Target repo:** https://github.com/KnowsoftCloudAir/FMSS_Smark_Multi_user_online  
**Live site:** https://knowosft-erp.onrender.com/

---

## 1. Role rename: Super Admin → General Admin

| Old | New | Purpose |
|-----|-----|---------|
| `superadmin` | `general_admin` | Platform-level only: approve/reject companies, issue licenses, technical corrections |
| Company users | unchanged | company_admin, finance, program, etc. |

**General Admin does NOT** see company finance modules.  
**General Admin ONLY** sees:
- Registered firms list
- Approve / Reject / Suspend / Issue license
- Technical correction queue
- Platform backup

Login credentials (seeded):
```
Username: general_admin
Password: GeneralAdmin@FMSS2026!
```

---

## 2. Straightforward registration

Registration is reduced to 5 fields only:

1. Company Name *
2. Company Slug * (auto-suggested from name)
3. Admin Full Name *
4. Admin Email *
5. Admin Password * (min 10, mixed case + number + symbol)

No address required on first step. After approval the company admin completes profile.

Status flow:
```
pending → approved (by General Admin) → active
```

---

## 3. Multi-currency (expanded)

Supported currencies (seeded + selectable):

| Code | Symbol | Name |
|------|--------|------|
| NGN | ₦ | Nigerian Naira |
| USD | $ | US Dollar |
| EUR | € | Euro |
| GBP | £ | British Pound |
| GHS | ₵ | Ghanaian Cedi |
| KES | KSh | Kenyan Shilling |
| ZAR | R | South African Rand |
| XOF | CFA | West African CFA Franc |
| CAD | C$ | Canadian Dollar |
| CNY | ¥ | Chinese Yuan |

Each company has:
- `reporting_currency_code` / `reporting_currency_symbol` (books currency)
- Exchange rates table (manual or import)
- Foreign documents convert at document date rate

---

## 4. Project-based budgets (IFRS-aligned)

Budgets are **owned by projects**, not free-floating codes.

Structure:
```
Project
  └── Budget lines (by expense category / IFRS class)
        └── Expense codes (debit / credit accounts)
              └── Payment requests / Journals / Procurement
```

IFRS presentation classes used on COA and reports:
- Assets (current / non-current)
- Liabilities (current / non-current)
- Equity
- Income (revenue)
- Expenses (by nature or function)
- Cash & cash equivalents

Workflow:
1. Create Project (code, name, start/end, budget ceiling)
2. Add budget lines under the project
3. Link expense codes to budget lines + COA
4. All payments / POs must reference a project
5. Project dashboard shows: budget vs actual, burn rate, variance, charts

---

## 5. Project financial analysis & charts

Each project has a dedicated analysis view:

- Budget vs Actual (bar)
- Monthly spend trend (line)
- Expense breakdown by category (doughnut)
- Commitment (open POs) vs Paid vs Remaining
- Variance table with % and absolute
- Export PDF / Excel

API endpoints:
- `GET /api/projects/{id}/analysis`
- `GET /api/projects/{id}/charts`
- `GET /api/reports/project/{id}/pdf`

---

## 6. Full finance (input → workflow → output)

| Module | Input | Workflow | Output |
|--------|-------|----------|--------|
| COA | IFRS-classed accounts | Active/inactive | Trial balance, FS |
| Budgets | Project + amount | Variance tracking | Budget vs actual report |
| Payments | Request form | submit → program → finance → paid | Voucher, GL post |
| Journals | Manual double-entry | Post | GL, TB |
| Bank recon | Statement lines | Match / adjust | Recon statement |
| Assets | Register + cost | Depreciation (optional) | Asset register PDF |
| Inventory | Items + movements | Issue / receive | Stock valuation |
| Procurement | RFQ → Quote → PO → GRN → Invoice | Committee scoring | PO, GRN, payment link |

All money movements post to GL when status reaches `paid` / `posted`.

---

## 7. Procurement (fixed end-to-end)

Correct status chain:

```
RFQ draft
  → open (published)
  → evaluation (quotes scored by committee)
  → awarded (winner selected)
  → PO created (pending_officer)
  → PO approved
  → GRN (goods received, conditions checked)
  → Invoice submitted
  → Payment request auto-linked
  → paid
```

Fixes applied:
- Committee members can score only assigned RFQs
- Winner selection requires all mandatory scores
- PO cannot be created without awarded quote
- GRN requires quantity / integrity / shelf-life flags
- Invoice cannot skip GRN
- Payment request inherits project + COA from PO

---

## 8. General Admin approval page

After login as `general_admin`:

Sidebar shows **only**:
- Owner approvals (Registered Firms)
- Technical corrections
- Platform backup

Registered Firms table columns:
| Name | Slug | Status | License Expiry | Actions |

Actions:
- **Approve** (sets status=approved, issues 1-year license)
- **Reject**
- **Suspend**
- **Issue / Extend license**

---

## 9. Files to update (this package)

```
backend/
  models_upgrade.py      → new / altered models (Project, Currency, rates, role)
  general_admin_api.py   → approval + correction endpoints
  project_finance_api.py → project analysis + charts data
  seed_upgrade.py        → currencies, general_admin user, sample projects

frontend/
  general_admin.js       → owner form + approval UI (fixes missing handlers)
  project_charts.js      → Chart.js project dashboards
  registration_clean.js  → simplified 5-field registration
  styles_professional.css→ cleaner, adult UI overrides

docs/
  UPGRADE_GUIDE.md       → this file
```

---

## 10. Deploy steps (Render)

1. Merge the upgrade files into your repo.
2. Update `main.py` to include the new routers.
3. Change seed from `superadmin` → `general_admin`.
4. Clear Render build cache and redeploy.
5. Login: `general_admin` / `GeneralAdmin@FMSS2026!`
6. Open **Owner approvals** → approve pending firms.

---

## 11. Design principles applied

- No cartoon / toy language in UI
- Clear role separation (General Admin ≠ Company Admin)
- Project is the spine of all money
- IFRS vocabulary on forms and reports
- Every workflow has a visible status and audit trail
- Registration is 5 fields, not a form marathon
- Charts are real (Chart.js) and project-scoped
