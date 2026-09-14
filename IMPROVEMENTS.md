# Knowsoft FMSS ERP — Applied Improvements (Sept 2026)

## Changes in this build

### 1. RFQ Winner declaration
- Existing `POST /api/procurement/rfqs/{id}/declare-winner` retained and confirmed.
- RFQ detail now returns `pending_scorers` (committee members who have not yet scored).

### 2. Delete mistaken RFQ / quote links
- `DELETE /api/procurement/rfqs/{id}` — only if no quotes submitted.
- `DELETE /api/procurement/rfqs/{id}/links/{link_id}` — revoke a vendor link.

### 3. Committee scores only once
- `score_quote` now returns **400** if the member already scored that quote (no overwrite).

### 4. Receive Income dropdowns
- Use existing `/api/finance/coa`, `/api/finance/expense-codes`, budget/project code endpoints.
- Ensure frontend fetches these on the Receive Income page mount (see frontend notes).

### 5. Approval queues
- `list_payments` is role-filtered:
  - **program**: only `submitted`
  - **finance**: only `program_approved`
  - **originator**: own requests (including `rejected` for resubmit)
  - **admin**: all
- Reject sets `status=rejected` so item leaves approver list and returns to originator.

### 6. Real-time ledger
- Payments already call `post_double_entry` on mark-paid.
- Income posting and journals continue to write `JournalEntry` rows used by TB and statements.

### 7–8. Currency
- Company reporting currency still on Company model.
- New: `GET/POST /api/finance/exchange-rates`
- New: `POST /api/reports/convert` — converts IFRS position/performance by rate factor.

### 9. SoFP always balances + audit
- Statement of Financial Position auto-applies any difference to **Capital** with a clear balancing note.
- Journal entries and approval logs remain the audit trail; drill-down can use `source_type` + `source_id`.

### Login / Trial
- Login page demo credentials reduced to a single compact block.
- **New company registration auto-activates a 15-day free trial** (no superadmin wait).
- Demo company remains for 24-hour style evaluation using `demo/admin`.

## Deploy notes
1. Delete old SQLite DB after schema changes so tables recreate.
2. Restart uvicorn / Render service.
3. Test score uniqueness, RFQ delete, income dropdowns, approval queues, SoFP balance.
