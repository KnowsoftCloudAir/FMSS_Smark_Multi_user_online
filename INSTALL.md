# Install — Professional Upgrade Package

## What this package fixes / adds

1. **General Admin** (replaces Super Admin) — approvals & technical corrections only  
2. **Working Owner console login** (the missing JS handlers)  
3. **Registered Firms approval table** that actually loads and has Approve / Reject  
4. **Project-based budgets** + project financial analysis API  
5. **Charts** for budget vs actual, expense mix, monthly trend  
6. **10 currencies** (NGN, USD, EUR, GBP, GHS, KES, ZAR, XOF, CAD, CNY)  
7. **Cleaner registration** messaging  
8. **Procurement** status chain documented and API-aligned  

---

## Step-by-step

### A. Backend

1. Copy into your repo:

```
backend/general_admin_api.py
backend/project_finance_api.py
```

2. In `backend/main.py` add near the other routers:

```python
from general_admin_api import router as ga_router, ensure_general_admin
from project_finance_api import router as project_router

app.include_router(ga_router)
app.include_router(project_router)
```

3. In your startup / `init_defaults` call:

```python
ensure_general_admin(db)
```

4. (Optional but recommended) Rename seed user from `superadmin` to `general_admin`  
   Password: `GeneralAdmin@FMSS2026!`

### B. Frontend

1. Copy:

```
frontend/general_admin.js
frontend/project_charts.js
frontend/registration_clean.js
```

2. In `frontend/index.html` (before `</body>`), add:

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="/frontend/app.js"></script>
<script src="/frontend/general_admin.js"></script>
<script src="/frontend/project_charts.js"></script>
<script src="/frontend/registration_clean.js"></script>
```

(Adjust paths if your static mount is different, e.g. `/static/js/...`.)

3. Ensure the sidebar still has:

```html
<a href="#" class="nav-item super-only" data-view="superadmin" style="display:none;">
  <span class="icon">🛡️</span> Firm Approvals
</a>
```

4. Ensure `#view-superadmin` contains the Registered Firms table (`#companies-table`).

5. Optional project analysis section (add inside a project detail view):

```html
<div id="proj-analysis-summary"></div>
<div class="chart-grid">
  <canvas id="proj-budget-chart"></canvas>
  <canvas id="proj-expense-chart"></canvas>
  <canvas id="proj-trend-chart"></canvas>
</div>
```

Call `showProjectAnalysis(projectId)` when the user opens a project.

### C. Deploy (Render)

1. Commit & push.
2. Render Dashboard → your service → **Manual Deploy → Clear build cache & deploy**.
3. After deploy, open: https://knowosft-erp.onrender.com/
4. Click **Owner console**.
5. Login:
   - Username: `general_admin`
   - Password: `GeneralAdmin@FMSS2026!`
6. You should land on **Firm Approvals** with the companies table and Approve buttons.

### D. Fallback if old superadmin still exists

You can still use:

- Username: `superadmin`  
- Password: `SuperAdmin@FMSS2026!`

The new code accepts both roles during transition.

---

## Quick test checklist

- [ ] Owner console form appears when link is clicked  
- [ ] general_admin login succeeds  
- [ ] Firm Approvals menu is visible  
- [ ] Registered Firms table loads  
- [ ] Pending company shows Approve / Reject  
- [ ] Approve sets status=approved and issues license  
- [ ] Company admin can then sign in as `slug/admin`  
- [ ] `/api/projects/meta/currencies` returns 10 currencies  
- [ ] Project analysis endpoint returns budget / spent / charts data  

---

## Design rules applied

- General Admin ≠ Company Admin (hard separation)  
- Approval is the only platform job  
- Budgets hang under projects  
- Reports speak IFRS-style classes  
- Registration is short  
- UI language is adult and operational, not toy-like  
