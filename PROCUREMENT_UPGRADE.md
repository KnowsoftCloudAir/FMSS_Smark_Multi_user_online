# Procurement System Upgrade – CONTRAconnect / UNDP TORs

## Summary
The FMSS procurement module has been upgraded to support robust Long-Term Agreement (LTA) procurement aligned with the attached Terms of Reference for:

- **Lot 1**: Procurement and Supply of Family Planning Commodities (Implanon, Jadelle, Injectables, IUCD, COCs, Condoms)
- **Lot 2**: Medical Consumables & IPC (gloves, syringes, needles, pregnancy tests, iodine, xylocaine, ABHR, sharps bins, etc.)

## Key Features Added

### 1. Vendor Eligibility (mandatory before bidding)
- Experience years (min 3), similar contracts (min 2)
- NAFDAC status, PCN license (Lot 2), ISO 13485 / cGMP flags
- Logistics footprint (delivery to Benin City)
- Eligibility status: pending | eligible | ineligible
- Soft-delete flag `is_demo` for cleanable demo data

### 2. RFQ / LTA structure
- `lot` field (Lot 1 FP / Lot 2 Consumables)
- Technical specs text (from TOR annexes)
- Evaluation method: `lowest_price_technically_compliant` (Pass/Fail technical → lowest price)
- Min shelf-life months, delivery location, LTA duration (18 months)

### 3. Bid submission with hard validation gate
- Mandatory PDF document uploads per lot (`/api/procurement/quotes/{id}/upload-doc`)
- Checklist endpoint (`/docs-checklist`) returns required vs uploaded
- **Cannot submit** until:
  - All mandatory PDF types uploaded
  - Shelf-life commitment flag set
  - Manufacturer authorization flag set
- Endpoint: `POST /api/procurement/quotes/{id}/submit`

### 4. Evaluation workflow (committee)
1. Preliminary (docs complete) → `preliminary_pass`
2. Technical Pass/Fail → `POST .../evaluate-technical`
3. Financial ranking among technical passers → `POST /api/procurement/rfqs/{id}/rank-financial`
4. Award + PO creation (existing flow)

### 5. Delivery / Goods Receipt
- All five conditions must be true for acceptance:
  - Quantities OK
  - Package integrity OK
  - Shelf-life OK (≥6 months FP / 75% or 24 months consumables)
  - Regulatory docs OK
  - Storage guidance document received
- Endpoint: `POST /api/procurement/pos/{id}/goods-receipt`
- Status: accepted only when `all_conditions_met=true`

### 6. Invoice → Finance flow
- Create invoice after accepted GRN
- `POST /api/procurement/invoices/{id}/to-finance` creates a Payment Request in the Finance module
- PO status moves to `submitted_payment`

### 7. Demo data (deletable)
- Seeded RFQs: RFQ-FP-LOT1, RFQ-MED-LOT2, plus legacy RFQ-0001…0004
- Vendors: PharmaLink, MediCare, SafeHealth + legacy
- Quotes at stages: technical_eval, open, awarded, rejected
- GRN-0001 + INV-TM-88421 flowing to finance
- **Delete all demo**: `DELETE /api/procurement/demo-data` (admin only)

### 8. Passwords changed (Oct 2026)
```
demo/program  / Program@FMSS2026!
demo/finance  / Finance@FMSS2026!
demo/admin    / Admin@FMSS2026!
superadmin    / SuperAdmin@FMSS2026!
```

## Mandatory document types (by lot)
**Lot 1 FP**: cac, tax_clearance, nafdac, maf, shelf_life_commitment, sop_recall, technical_proposal, financial_proposal, experience_letter

**Lot 2 Consumables**: + iso_cert, pcn_license, logistics_proof

## Files touched
- `backend/models.py` – Vendor, RFQ, Quote extended; GoodsReceipt, ProcurementInvoice added
- `backend/main.py` – seed, passwords, new API endpoints
- `requirements.txt` – werkzeug
- `README.md` – new passwords

## Next steps for production
1. Wire frontend forms for PDF upload + checklist UI
2. Map exact TOR annex quantities into line-item tables if needed
3. Add NAFDAC/MAS PIN verification hooks
4. Configure real storage paths and virus scanning for uploads
