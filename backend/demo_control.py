"""
Demo data load / clear — usable by company_admin (own company) and General Admin (demo company).
"""
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models import (
    User, Company, ChartOfAccount, BudgetCode, ExpenseCode, PaymentRequest,
    Asset, InventoryItem, Vendor, ProjectCode, PaymentApprovalLog,
)
from auth import get_current_active_user, get_password_hash, generate_license_key

router = APIRouter(prefix="/api/demo", tags=["Demo data"])


def _require_company_or_platform(user: User = Depends(get_current_active_user)):
    if user.role in ("superadmin", "general_admin", "owner"):
        return user
    if user.role in ("company_admin", "admin", "finance"):
        return user
    raise HTTPException(403, "Only company admin / finance or General Admin can manage demo data")


@router.post("/load")
def load_demo(user: User = Depends(_require_company_or_platform), db: Session = Depends(get_db)):
    """Seed or refresh demo sample data for the current company (or 'demo' for platform admin)."""
    # Resolve target company
    if user.company_id:
        co = db.query(Company).filter(Company.id == user.company_id).first()
    else:
        co = db.query(Company).filter(Company.slug == "demo").first()
        if not co:
            co = Company(
                name="Demo Organization",
                slug="demo",
                address="Lagos, Nigeria",
                status="approved",
                license_key=generate_license_key("demo") if callable(generate_license_key) else "DEMO-KEY",
                license_expires=date.today() + timedelta(days=365),
                approved_at=datetime.utcnow(),
                approved_by=user.username,
            )
            db.add(co)
            db.commit()
            db.refresh(co)

    if not co:
        raise HTTPException(400, "No company to seed")

    if co.status not in ("approved", "active") and user.role not in ("superadmin", "general_admin", "owner"):
        raise HTTPException(403, "Company not approved yet")

    # Ensure basic COA
    existing_coa = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == co.id).count()
    added = {"coa": 0, "budgets": 0, "expenses": 0, "payments": 0, "assets": 0, "inventory": 0, "vendors": 0, "projects": 0}

    if existing_coa == 0:
        coa_rows = [
            ("1000", "Cash at Bank - Main", "Cash"),
            ("1100", "Petty Cash", "Cash"),
            ("1200", "Accounts Receivable", "Asset"),
            ("1500", "Furniture & Fittings", "Asset"),
            ("1510", "IT Equipment", "Asset"),
            ("2000", "Accounts Payable", "Liability"),
            ("3000", "Retained Earnings", "Equity"),
            ("4000", "Programme Income", "Income"),
            ("5000", "Staff Salaries", "Expense"),
            ("5100", "Office Rent", "Expense"),
            ("5200", "Travel & Transport", "Expense"),
            ("5300", "Training & Workshops", "Expense"),
            ("5400", "Utilities & Communications", "Expense"),
            ("5500", "Programme Supplies", "Expense"),
            ("5600", "Professional Fees", "Expense"),
            ("5700", "Bank Charges", "Expense"),
        ]
        for code, name, typ in coa_rows:
            db.add(ChartOfAccount(company_id=co.id, code=code, name=name, account_type=typ))
            added["coa"] += 1
        db.commit()

    # Project
    proj = db.query(ProjectCode).filter(ProjectCode.company_id == co.id, ProjectCode.code == "PRJ-OPS").first()
    if not proj:
        kwargs = dict(company_id=co.id, code="PRJ-OPS")
        if hasattr(ProjectCode, "name"):
            kwargs["name"] = "Operations 2026"
        if hasattr(ProjectCode, "budget_amount"):
            kwargs["budget_amount"] = 25000000
        proj = ProjectCode(**kwargs)
        db.add(proj)
        db.commit()
        db.refresh(proj)
        added["projects"] += 1

    # Budgets
    if db.query(BudgetCode).filter(BudgetCode.company_id == co.id).count() == 0:
        for code, desc, amt in [
            ("BUD-OPS-2026", "Operations & Admin 2026", 8000000),
            ("BUD-HEALTH-2026", "Health Programme 2026", 12000000),
            ("BUD-EDU-2026", "Education Support 2026", 5000000),
        ]:
            db.add(BudgetCode(company_id=co.id, code=code, description=desc, amount=amt, spent=0))
            added["budgets"] += 1
        db.commit()

    # Expense codes
    if db.query(ExpenseCode).filter(ExpenseCode.company_id == co.id).count() == 0:
        bud = db.query(BudgetCode).filter(BudgetCode.company_id == co.id).first()
        debit = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == co.id, ChartOfAccount.code == "5100").first()
        credit = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == co.id, ChartOfAccount.code == "1000").first()
        for code, desc in [
            ("EXP-RENT", "Office rent"),
            ("EXP-SAL", "Staff salaries"),
            ("EXP-TRV", "Field travel"),
            ("EXP-SUP", "Programme supplies"),
        ]:
            db.add(ExpenseCode(
                company_id=co.id, code=code, description=desc,
                budget_code_id=bud.id if bud else None,
                default_debit_account_id=debit.id if debit else None,
                default_credit_account_id=credit.id if credit else None,
            ))
            added["expenses"] += 1
        db.commit()

    # Vendors
    if db.query(Vendor).filter(Vendor.company_id == co.id).count() == 0:
        for num, name in [("V-001", "MedSupply Co"), ("V-002", "TechMart Nigeria"), ("V-003", "Training Hub Ltd")]:
            kwargs = dict(company_id=co.id, vendor_number=num, name=name)
            if hasattr(Vendor, "is_demo"):
                kwargs["is_demo"] = True
            db.add(Vendor(**kwargs))
            added["vendors"] += 1
        db.commit()

    # Assets
    if db.query(Asset).filter(Asset.company_id == co.id).count() == 0:
        admin = db.query(User).filter(User.company_id == co.id).first()
        for num, name, cat, cost, nbv in [
            ("FA-001", "Toyota Hilux 2022", "Motor Vehicles", 18500000, 14800000),
            ("FA-002", "Dell Laptops (10)", "IT Equipment", 4500000, 3600000),
            ("FA-003", "Office Furniture Set", "Furniture", 1200000, 900000),
        ]:
            kwargs = dict(
                company_id=co.id, asset_number=num, asset_name=name, category=cat,
                cost=cost, nbv=nbv, condition="Good",
            )
            if hasattr(Asset, "created_by") and admin:
                kwargs["created_by"] = admin.id
            if hasattr(Asset, "is_demo"):
                kwargs["is_demo"] = True
            db.add(Asset(**kwargs))
            added["assets"] += 1
        db.commit()

    # Inventory
    if db.query(InventoryItem).filter(InventoryItem.company_id == co.id).count() == 0:
        for code, name, cat, cost, qty in [
            ("INV-001", "Medical gloves (box)", "Consumables", 4500, 200),
            ("INV-002", "A4 Paper ream", "Stationery", 3200, 50),
            ("INV-003", "First aid kit", "Medical", 15000, 12),
        ]:
            kwargs = dict(company_id=co.id, item_code=code, name=name, category=cat)
            if hasattr(InventoryItem, "unit_cost"):
                kwargs["unit_cost"] = cost
            if hasattr(InventoryItem, "balance_qty"):
                kwargs["balance_qty"] = qty
            elif hasattr(InventoryItem, "quantity"):
                kwargs["quantity"] = qty
            if hasattr(InventoryItem, "is_demo"):
                kwargs["is_demo"] = True
            try:
                db.add(InventoryItem(**kwargs))
                added["inventory"] += 1
            except Exception:
                db.rollback()
        db.commit()

    # Sample payment if none
    if db.query(PaymentRequest).filter(PaymentRequest.company_id == co.id).count() == 0:
        admin = db.query(User).filter(User.company_id == co.id).first()
        bud = db.query(BudgetCode).filter(BudgetCode.company_id == co.id).first()
        exp = db.query(ExpenseCode).filter(ExpenseCode.company_id == co.id).first()
        debit = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == co.id, ChartOfAccount.code == "5100").first()
        credit = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == co.id, ChartOfAccount.code == "1000").first()
        if admin and bud and exp:
            pr = PaymentRequest(
                company_id=co.id,
                request_no="PR-DEMO-0001",
                requester_id=admin.id,
                budget_code_id=bud.id,
                expense_code_id=exp.id,
                amount=850000,
                narration="Demo office rent Q1",
                payee_name="Property Holdings Ltd",
                status="submitted",
            )
            if hasattr(pr, "debit_account_id") and debit:
                pr.debit_account_id = debit.id
            if hasattr(pr, "credit_account_id") and credit:
                pr.credit_account_id = credit.id
            if hasattr(pr, "amount_in_words"):
                pr.amount_in_words = "Eight hundred and fifty thousand only"
            if hasattr(pr, "project_code_id") and proj:
                pr.project_code_id = proj.id
            db.add(pr)
            added["payments"] += 1
            db.commit()

    return {
        "ok": True,
        "message": f"Demo data ready for {co.name}",
        "company": co.slug,
        "added": added,
    }


@router.post("/clear")
def clear_demo(user: User = Depends(_require_company_or_platform), db: Session = Depends(get_db)):
    """Remove demo-flagged sample data. Falls back to clearing sample request numbers for demo company."""
    if user.company_id:
        cid = user.company_id
    else:
        co = db.query(Company).filter(Company.slug == "demo").first()
        if not co:
            return {"ok": True, "message": "No demo company", "removed": 0}
        cid = co.id

    removed = 0

    # Prefer is_demo flag when present
    for model in (PaymentRequest, Asset, InventoryItem, Vendor):
        try:
            if hasattr(model, "is_demo"):
                n = db.query(model).filter(model.company_id == cid, model.is_demo == True).delete()
                removed += n or 0
        except Exception:
            db.rollback()

    # Clear sample payments by number pattern
    try:
        n = db.query(PaymentRequest).filter(
            PaymentRequest.company_id == cid,
            PaymentRequest.request_no.like("PR-DEMO%"),
        ).delete(synchronize_session=False)
        removed += n or 0
    except Exception:
        db.rollback()

    # Clear sample assets by number
    try:
        n = db.query(Asset).filter(
            Asset.company_id == cid,
            Asset.asset_number.like("FA-00%"),
        ).delete(synchronize_session=False)
        removed += n or 0
    except Exception:
        db.rollback()

    try:
        n = db.query(InventoryItem).filter(
            InventoryItem.company_id == cid,
            InventoryItem.item_code.like("INV-00%"),
        ).delete(synchronize_session=False)
        removed += n or 0
    except Exception:
        db.rollback()

    try:
        n = db.query(Vendor).filter(
            Vendor.company_id == cid,
            Vendor.vendor_number.in_(["V-001", "V-002", "V-003"]),
        ).delete(synchronize_session=False)
        removed += n or 0
    except Exception:
        db.rollback()

    db.commit()
    return {"ok": True, "message": f"Cleared {removed} demo records", "removed": removed}
