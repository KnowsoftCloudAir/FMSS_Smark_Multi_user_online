from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from pathlib import Path
import os, shutil, re, json, zipfile, io, csv, secrets

from database import engine, get_db, Base
from models import (
    User, Company, AuditLog, CompanySettings, PasswordResetToken,
    ChartOfAccount, BudgetCode, ExpenseCode, PaymentRequest, PaymentApprovalLog, Asset,
    PaymentAttachment, ProjectCode, JournalEntry, InventoryItem, InventoryMovement,
    Vendor, AssetAccountingEntry, BankReconState, CorrectionRequest, BankStatementSession,
    RFQ, RFQQuoteLink, RFQQuote, RFQCommitteeMember, RFQQuoteScore, PurchaseOrder, PaymentLine, RFQLineItem, RFQCommitteeInvite, IncomeReceipt, IncomeReceiptLine, RFQQuoteLine
)
from schemas import (
    Token, UserCreate, UserUpdate, UserOut, CompanyRegister, CompanyOut, CompanyUpdate,
    LicenseIssue, PasswordChange, PasswordResetRequest, PasswordResetConfirm,
    COAIn, BudgetCodeIn, ExpenseCodeIn, PaymentRequestIn, PaymentAction, AssetIn,
    CompanySettingsOut
)
from amount_words import amount_to_words
from auth import (
    create_access_token, get_password_hash, verify_password,
    get_current_active_user, get_superadmin, get_company_admin,
    require_roles, check_company_license, generate_reset_token, generate_license_key,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Knowsoft FMSS ERP", version="2.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = Path(__file__).parent.parent / "static"
IMAGES_DIR = STATIC_DIR / "images"
UPLOADS_DIR = STATIC_DIR / "uploads"
BACKUP_DIR = STATIC_DIR / "backups"
for d in (IMAGES_DIR, UPLOADS_DIR, BACKUP_DIR):
    d.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_DATA = {".csv", ".xlsx", ".xls", ".pdf"}


def audit(db, company_id, user, action, details):
    db.add(AuditLog(
        company_id=company_id,
        user_id=user.id if user else None,
        username=user.username if user else "system",
        action=action,
        details=details,
    ))
    db.commit()


def init_defaults(db: Session):
    if not db.query(CompanySettings).first():
        db.add(CompanySettings(org_name="Knowsoft FMSS ERP"))
        db.commit()

    # Platform superadmin (no company)
    sa = db.query(User).filter(User.username == "superadmin", User.company_id.is_(None)).first()
    if not sa:
        sa = User(
            company_id=None,
            username="superadmin",
            email="superadmin@knowsoft.local",
            full_name="Platform Super Admin",
            hashed_password=get_password_hash("Knowsoft@Super0160!"),
            role="superadmin",
            is_active=True,
            can_access_finance=True,
            can_access_inventory=True,
            can_access_assets=True,
            can_edit_assets=True,
            can_access_vendors=True,
            can_access_reports=True,
            can_approve_payment=True,
        )
        db.add(sa)
        db.commit()
        print("✅ Superadmin: superadmin / Knowsoft@Super0160!")

    demo = db.query(Company).filter(Company.slug == "demo").first()
    if not demo:
        demo = Company(
            name="Demo Organization",
            slug="demo",
            address="Lagos, Nigeria",
            status="approved",
            license_key=generate_license_key("demo"),
            license_expires=date.today() + timedelta(days=365),
            approved_at=datetime.utcnow(),
            approved_by="system",
        )
        db.add(demo)
        db.commit()
        db.refresh(demo)
        admin = User(
            company_id=demo.id,
            username="admin",
            email="admin@demo.local",
            full_name="Demo Company Admin",
            hashed_password=get_password_hash("Admin@Knowsoft1!"),
            role="company_admin",
            is_active=True,
            can_access_finance=True,
            can_access_inventory=True,
            can_access_assets=True,
            can_edit_assets=True,
            can_access_vendors=True,
            can_access_reports=True,
            can_approve_payment=True,
        )
        finance = User(
            company_id=demo.id,
            username="finance",
            email="finance@demo.local",
            full_name="Demo Finance Officer",
            hashed_password=get_password_hash("Finance@Knowsoft1!"),
            role="finance",
            is_active=True,
            can_access_finance=True,
            can_access_assets=True,
            can_access_reports=True,
            can_approve_payment=True,
        )
        program = User(
            company_id=demo.id,
            username="program",
            email="program@demo.local",
            full_name="Demo Program Manager",
            hashed_password=get_password_hash("Program@Knowsoft1!"),
            role="program",
            is_active=True,
            can_access_reports=True,
            can_approve_payment=True,
        )
        db.add_all([admin, finance, program])
        db.commit()
        db.refresh(admin)
        db.refresh(finance)
        db.refresh(program)

        # ---- Full sample financial data ----
        coa_rows = [
            ("1000", "Cash at Bank - Main", "Cash"),
            ("1100", "Petty Cash", "Cash"),
            ("1200", "Accounts Receivable", "Asset"),
            ("1500", "Furniture & Fittings", "Asset"),
            ("1510", "IT Equipment", "Asset"),
            ("1520", "Motor Vehicles", "Asset"),
            ("2000", "Accounts Payable", "Liability"),
            ("3000", "Retained Earnings", "Equity"),
            ("4000", "Grant Income", "Income"),
            ("4100", "Other Income", "Income"),
            ("5000", "Staff Salaries", "Expense"),
            ("5100", "Office Rent", "Expense"),
            ("5200", "Travel & Transport", "Expense"),
            ("5300", "Training & Workshops", "Expense"),
            ("5400", "Utilities & Communications", "Expense"),
            ("5500", "Programme Supplies", "Expense"),
            ("5600", "Professional Fees", "Expense"),
            ("5700", "Bank Charges", "Expense"),
        ]
        coa_map = {}
        for code, name, typ in coa_rows:
            row = ChartOfAccount(company_id=demo.id, code=code, name=name, account_type=typ)
            db.add(row)
            db.flush()
            coa_map[code] = row.id

        budgets = [
            ("BUD-HEALTH-2026", "Health Programme 2026", 25000000, program.id),
            ("BUD-EDU-2026", "Education Support 2026", 18000000, program.id),
            ("BUD-OPS-2026", "Operations & Admin 2026", 8000000, finance.id),
            ("BUD-CAPEX-2026", "Capital Expenditure 2026", 12000000, admin.id),
        ]
        bud_map = {}
        for code, desc, amt, approver in budgets:
            b = BudgetCode(company_id=demo.id, code=code, description=desc, amount=amt, spent=0, default_approver_id=approver)
            db.add(b)
            db.flush()
            bud_map[code] = b.id

        expenses = [
            ("EXP-SAL", "Monthly staff salaries", bud_map["BUD-OPS-2026"], coa_map["5000"], coa_map["1000"]),
            ("EXP-RENT", "Office rent payment", bud_map["BUD-OPS-2026"], coa_map["5100"], coa_map["1000"]),
            ("EXP-TRV", "Field travel allowances", bud_map["BUD-HEALTH-2026"], coa_map["5200"], coa_map["1000"]),
            ("EXP-TRN", "Community training workshop", bud_map["BUD-EDU-2026"], coa_map["5300"], coa_map["1000"]),
            ("EXP-SUP", "Medical supplies for outreach", bud_map["BUD-HEALTH-2026"], coa_map["5500"], coa_map["1000"]),
            ("EXP-IT", "Laptops and peripherals", bud_map["BUD-CAPEX-2026"], coa_map["1510"], coa_map["1000"]),
            ("EXP-UTIL", "Electricity and internet", bud_map["BUD-OPS-2026"], coa_map["5400"], coa_map["1000"]),
            ("EXP-FEE", "External audit fees", bud_map["BUD-OPS-2026"], coa_map["5600"], coa_map["1000"]),
        ]
        exp_map = {}
        for code, desc, bid, debit, credit in expenses:
            e = ExpenseCode(
                company_id=demo.id, code=code, description=desc,
                budget_code_id=bid, default_debit_account_id=debit, default_credit_account_id=credit,
            )
            db.add(e)
            db.flush()
            exp_map[code] = e.id

        # Assets sample
        assets = [
            ("FA-001", "Toyota Hilux 2022", "Motor Vehicles", "Head Office", 18500000, 14800000, "Good", "Yes"),
            ("FA-002", "Dell Latitude Laptops (10)", "IT Equipment", "ICT Store", 4500000, 3600000, "Good", "Yes"),
            ("FA-003", "Office Furniture Set", "Furniture", "Lagos Office", 1200000, 900000, "Fair", "No"),
            ("FA-004", "Generator 50KVA", "Plant & Machinery", "Compound", 3200000, 2560000, "Good", "Yes"),
            ("FA-005", "Old Desktop PCs (5)", "IT Equipment", "Archive", 450000, 50000, "Bad", "No"),
            ("FA-006", "Projector Epson", "IT Equipment", "Training Hall", 380000, 266000, "Good", "Yes"),
            ("FA-007", "Missing Tablet", "IT Equipment", "Field", 180000, 0, "Lost", "No"),
        ]
        for num, name, cat, loc, cost, nbv, cond, ins in assets:
            db.add(Asset(
                company_id=demo.id, asset_number=num, asset_name=name, category=cat,
                location=loc, cost=cost, nbv=nbv, condition=cond, insurance=ins,
                created_by=admin.id,
            ))

        # Payment requests across workflow stages
        from datetime import timedelta as _td
        samples = [
            # paid
            ("PR-202603-0001", admin.id, bud_map["BUD-OPS-2026"], exp_map["EXP-RENT"], 850000,
             "Office rent Q1 2026", "Property Holdings Ltd", coa_map["5100"], coa_map["1000"],
             program.id, "paid", program.id, finance.id),
            ("PR-202603-0002", finance.id, bud_map["BUD-OPS-2026"], exp_map["EXP-SAL"], 4200000,
             "March 2026 payroll", "Staff Payroll Account", coa_map["5000"], coa_map["1000"],
             program.id, "paid", program.id, finance.id),
            # finance approved - ready to pay
            ("PR-202603-0003", admin.id, bud_map["BUD-CAPEX-2026"], exp_map["EXP-IT"], 2750000,
             "Purchase of 5 project laptops", "TechMart Nigeria", coa_map["1510"], coa_map["1000"],
             admin.id, "finance_approved", program.id, finance.id),
            # program approved - awaiting finance
            ("PR-202603-0004", program.id, bud_map["BUD-HEALTH-2026"], exp_map["EXP-SUP"], 1850000,
             "Outreach medical kits - Kano State", "MedSupply Co", coa_map["5500"], coa_map["1000"],
             program.id, "program_approved", program.id, None),
            # submitted - awaiting program
            ("PR-202603-0005", admin.id, bud_map["BUD-EDU-2026"], exp_map["EXP-TRN"], 980000,
             "Teacher capacity workshop - Abuja", "Training Hub Ltd", None, None,
             program.id, "submitted", None, None),
            ("PR-202603-0006", finance.id, bud_map["BUD-HEALTH-2026"], exp_map["EXP-TRV"], 640000,
             "Field monitoring travel - 3 states", "Various (staff)", None, None,
             program.id, "submitted", None, None),
            # rejected sample
            ("PR-202603-0007", admin.id, bud_map["BUD-OPS-2026"], exp_map["EXP-FEE"], 1500000,
             "Unbudgeted consultancy", "ConsultX Ltd", None, None,
             program.id, "rejected", None, None),
        ]
        for (rno, req, bid, eid, amt, narr, payee, debit, credit, appr, status, prog, fin) in samples:
            pr = PaymentRequest(
                company_id=demo.id, request_no=rno, requester_id=req,
                budget_code_id=bid, expense_code_id=eid, amount=amt,
                narration=narr, payee_name=payee,
                debit_account_id=debit, credit_account_id=credit,
                designated_approver_id=appr, status=status,
                program_approved_by=prog,
                program_approved_at=datetime.utcnow() - _td(days=2) if prog else None,
                finance_approved_by=fin,
                finance_approved_at=datetime.utcnow() - _td(days=1) if fin else None,
                paid_at=datetime.utcnow() - _td(hours=12) if status == "paid" else None,
                rejection_reason="Insufficient budget line justification" if status == "rejected" else "",
            )
            db.add(pr)
            db.flush()
            db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=req, action="submit", comment="Sample submission"))
            if status in ("program_approved", "finance_approved", "paid") and prog:
                db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=prog, action="program_approve", comment="Programme OK"))
            if status in ("finance_approved", "paid") and fin:
                db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=fin, action="finance_approve", comment="Accounts verified"))
            if status == "paid" and fin:
                db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=fin, action="pay", comment="Paid via transfer"))
            if status == "rejected":
                db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=program.id, action="reject", comment="Insufficient justification"))

        # Update spent on paid items
        paid_rent = db.query(BudgetCode).filter(BudgetCode.id == bud_map["BUD-OPS-2026"]).first()
        if paid_rent:
            paid_rent.spent = 850000 + 4200000  # rent + salary samples

        db.commit()
        
        # Inventory samples
        inv_items = [
            ("INV-001", "Paracetamol 500mg (box)", "Medical", "Health", 2500, 200),
            ("INV-002", "Exercise books (carton)", "Education", "Education", 18000, 50),
            ("INV-003", "Printer paper A4", "Stationery", "Admin", 4500, 80),
            ("INV-004", "Mosquito nets", "Medical", "Health", 3200, 150),
            ("INV-005", "USB flash drives 32GB", "IT", "ICT", 3500, 40),
        ]
        for code, name, cat, dept, cost, qty in inv_items:
            total = cost * qty
            item = InventoryItem(
                company_id=demo.id, item_code=code, item_name=name, category=cat,
                department=dept, cost_price=cost, qty_received=qty, qty_issued=0,
                balance_qty=qty, total_value=total, receive_method="Purchase",
                funding_source="Grant", debit_account_id=coa_map.get("5500"),
                credit_account_id=coa_map.get("1000"),
            )
            db.add(item)
            db.flush()
            if total > 0:
                eno = f"JE-SEED-INV-{code}"
                db.add(JournalEntry(company_id=demo.id, entry_no=eno, entry_date=date.today(),
                    source_type="inventory", source_id=item.id, account_id=coa_map["5500"],
                    description=f"Stock {code}", narration=name, debit=total, credit=0, created_by=admin.id))
                db.add(JournalEntry(company_id=demo.id, entry_no=eno, entry_date=date.today(),
                    source_type="inventory", source_id=item.id, account_id=coa_map["1000"],
                    description=f"Stock {code}", narration=name, debit=0, credit=total, created_by=admin.id))

        # Vendor samples
        vendors = [
            ("V-001", "MedSupply Co", "Lagos", "Yes", "Yes", "Yes", "Zenith Bank", 5000000, "Medical supplies"),
            ("V-002", "TechMart Nigeria", "Abuja", "Yes", "Yes", "No", "GTBank", 2750000, "IT equipment"),
            ("V-003", "Training Hub Ltd", "Abuja", "Yes", "No", "Yes", "Access Bank", 980000, "Training services"),
            ("V-004", "Property Holdings Ltd", "Lagos", "Yes", "Yes", "Yes", "UBA", 850000, "Office rent"),
        ]
        for num, name, addr, tax, reg, audit, bank, amt, desc in vendors:
            score = (25 if tax == "Yes" else 0) + (25 if reg == "Yes" else 0) + (25 if audit == "Yes" else 0) + 20
            db.add(Vendor(
                company_id=demo.id, vendor_number=num, name=name, address=addr,
                tax_clearance=tax, reg_with_govt=reg, audit_3yrs=audit, bank=bank,
                amount=amt, description=desc, score=score,
                debit_account_id=coa_map.get("5600"), credit_account_id=coa_map.get("2000"),
            ))

        # Project codes
        for code, name in [("PRJ-HLT", "Health Outreach"), ("PRJ-EDU", "Education Support"), ("PRJ-OPS", "Operations")]:
            db.add(ProjectCode(company_id=demo.id, code=code, name=name))

        # Update assets with assigned_to and accounts
        for a in db.query(Asset).filter(Asset.company_id == demo.id).all():
            a.assigned_to = a.assigned_to or "Head Office Pool"
            a.debit_account_id = a.debit_account_id or coa_map.get("1510")
            a.credit_account_id = a.credit_account_id or coa_map.get("1000")
            a.useful_life = a.useful_life or 5.0

        print("✅ Demo company seeded with COA, budgets, expenses, assets, payment workflow samples")

        # Second company still pending approval (for superadmin demo)
        pending = db.query(Company).filter(Company.slug == "sunrise-ngo").first()
        if not pending:
            pending = Company(
                name="Sunrise Community NGO",
                slug="sunrise-ngo",
                address="Abuja, FCT",
                status="pending",
            )
            db.add(pending)
            db.commit()
            db.refresh(pending)
            db.add(User(
                company_id=pending.id,
                username="admin",
                email="admin@sunrise.ngo",
                full_name="Sunrise Admin",
                hashed_password=get_password_hash("Sunrise@Admin1!"),
                role="company_admin",
                is_active=True,
                can_access_finance=True,
                can_access_inventory=True,
                can_access_assets=True,
                can_edit_assets=True,
                can_access_vendors=True,
                can_access_reports=True,
                can_approve_payment=True,
            ))
            db.commit()
            print("✅ Pending sample firm: sunrise-ngo (awaits superadmin approval)")

        print("✅ Demo company approved + licensed | admin / Admin@Knowsoft1!")


@app.on_event("startup")
def on_startup():
    db = next(get_db())
    try:
        init_defaults(db)
        try:
            cleanup_disposed_assets(db)
        except Exception as e:
            print("cleanup_disposed_assets:", e)
    finally:
        db.close()


# ===================== AUTH =====================
@app.post("/api/auth/register-company")
def register_company(data: CompanyRegister, db: Session = Depends(get_db)):
    slug = data.company_slug.lower().strip()
    if db.query(Company).filter(Company.slug == slug).first():
        raise HTTPException(400, "Company slug already taken")
    company = Company(
        name=data.company_name.strip(),
        slug=slug,
        address=data.address or "",
        status="pending",  # awaits superadmin approval
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    admin = User(
        company_id=company.id,
        username=data.admin_username.strip(),
        email=data.admin_email,
        full_name=data.admin_full_name or data.admin_username,
        hashed_password=get_password_hash(data.admin_password),
        role="company_admin",
        is_active=True,
        can_access_finance=True,
        can_access_inventory=True,
        can_access_assets=True,
        can_edit_assets=True,
        can_access_vendors=True,
        can_access_reports=True,
        can_approve_payment=True,
    )
    db.add(admin)
    db.commit()
    audit(db, company.id, admin, "REGISTER_COMPANY", f"Pending approval: {company.name}")
    return {
        "message": "Registration submitted. Awaiting Knowsoft superadmin approval and annual license.",
        "company": {"name": company.name, "slug": company.slug, "status": "pending"},
    }


@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    raw = form_data.username.strip()
    password = form_data.password
    company = None
    username = raw

    # Platform superadmin
    if raw == "superadmin" or raw.startswith("superadmin/"):
        username = "superadmin"
        user = db.query(User).filter(User.username == "superadmin", User.company_id.is_(None)).first()
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(401, "Incorrect username or password")
    else:
        if "/" in raw:
            slug, username = raw.split("/", 1)
            slug, username = slug.strip().lower(), username.strip()
            company = db.query(Company).filter(Company.slug == slug).first()
            if not company:
                raise HTTPException(401, "Invalid company or credentials")
        else:
            candidates = db.query(User).filter(User.username == username, User.is_active == True).all()
            # prefer non-null company
            candidates = [c for c in candidates if c.company_id is not None]
            if len(candidates) == 1:
                user = candidates[0]
                company = db.query(Company).filter(Company.id == user.company_id).first()
            elif len(candidates) > 1:
                raise HTTPException(401, "Multiple companies found. Login as company-slug/username")
            else:
                raise HTTPException(401, "Incorrect username or password")

        if company:
            check_company_license(db, company.id)

        user = db.query(User).filter(
            User.company_id == company.id,
            User.username == username,
            User.is_active == True,
        ).first()
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(401, "Incorrect username or password")

    user.last_login = datetime.utcnow()
    db.commit()
    audit(db, user.company_id, user, "LOGIN", f"Login {user.username}")

    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "company_id": user.company_id,
        "company_slug": company.slug if company else None,
    }, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "company_id": user.company_id,
            "company_name": company.name if company else "Knowsoft Platform",
            "company_slug": company.slug if company else None,
            "must_reset_password": user.must_reset_password,
            "can_access_finance": user.can_access_finance,
            "can_access_inventory": user.can_access_inventory,
            "can_access_assets": user.can_access_assets,
            "can_edit_assets": user.can_edit_assets,
            "can_access_vendors": user.can_access_vendors,
            "can_access_reports": user.can_access_reports,
            "can_approve_payment": user.can_approve_payment,
        },
    }


@app.get("/api/auth/me")
def me(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    company = None
    if current_user.company_id:
        company = db.query(Company).filter(Company.id == current_user.company_id).first()
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "company_id": current_user.company_id,
        "company_name": company.name if company else "Knowsoft Platform",
        "company_slug": company.slug if company else None,
        "must_reset_password": current_user.must_reset_password,
        "can_access_finance": current_user.can_access_finance,
        "can_access_inventory": current_user.can_access_inventory,
        "can_access_assets": current_user.can_access_assets,
        "can_edit_assets": current_user.can_edit_assets,
        "can_access_vendors": current_user.can_access_vendors,
        "can_access_reports": current_user.can_access_reports,
        "can_approve_payment": current_user.can_approve_payment,
    }


@app.post("/api/auth/change-password")
def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    current_user.hashed_password = get_password_hash(data.new_password)
    current_user.must_reset_password = False
    db.commit()
    audit(db, current_user.company_id, current_user, "CHANGE_PASSWORD", "Password changed")
    return {"message": "Password updated successfully"}


@app.post("/api/auth/request-reset")
def request_reset(data: PasswordResetRequest, db: Session = Depends(get_db)):
    q = db.query(User).filter(User.email == data.email)
    if data.company_slug:
        co = db.query(Company).filter(Company.slug == data.company_slug.lower()).first()
        if co:
            q = q.filter(User.company_id == co.id)
    user = q.first()
    # Always return success message (don't leak existence)
    if user:
        token = generate_reset_token()
        db.add(PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=2),
        ))
        db.commit()
        # In production: email the token. For demo we return it.
        return {
            "message": "If the account exists, a reset token was issued.",
            "reset_token": token,  # remove in production when email is wired
            "hint": "Use this token with /api/auth/confirm-reset (demo only)",
        }
    return {"message": "If the account exists, a reset token was issued."}


@app.post("/api/auth/confirm-reset")
def confirm_reset(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    row = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == data.token,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.utcnow(),
    ).first()
    if not row:
        raise HTTPException(400, "Invalid or expired reset token")
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise HTTPException(400, "User not found")
    user.hashed_password = get_password_hash(data.new_password)
    user.must_reset_password = False
    row.used = True
    db.commit()
    return {"message": "Password has been reset. You can sign in now."}


# ===================== SUPERADMIN =====================
@app.get("/api/superadmin/companies")
def list_all_companies(
    current_user: User = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    return db.query(Company).order_by(Company.created_at.desc()).all()


@app.post("/api/superadmin/companies/{company_id}/approve")
def approve_company(
    company_id: int,
    current_user: User = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    co.status = "approved"
    co.approved_at = datetime.utcnow()
    co.approved_by = current_user.username
    if not co.license_expires:
        co.license_key = generate_license_key(co.slug)
        co.license_expires = date.today() + timedelta(days=365)
    db.commit()
    audit(db, co.id, current_user, "APPROVE_COMPANY", f"Approved {co.name}")
    return {"message": f"{co.name} approved", "license_key": co.license_key, "license_expires": str(co.license_expires)}


@app.post("/api/superadmin/companies/{company_id}/reject")
def reject_company(
    company_id: int,
    current_user: User = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    co.status = "rejected"
    db.commit()
    audit(db, co.id, current_user, "REJECT_COMPANY", f"Rejected {co.name}")
    return {"message": "Company rejected"}


@app.post("/api/superadmin/companies/{company_id}/license")
def issue_license(
    company_id: int,
    data: LicenseIssue,
    current_user: User = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    if co.status != "approved":
        co.status = "approved"
        co.approved_at = datetime.utcnow()
        co.approved_by = current_user.username
    co.license_key = generate_license_key(co.slug)
    base = co.license_expires if co.license_expires and co.license_expires > date.today() else date.today()
    co.license_expires = base + timedelta(days=365 * data.years)
    co.license_notes = data.notes or ""
    db.commit()
    audit(db, co.id, current_user, "ISSUE_LICENSE", f"{data.years} year(s) until {co.license_expires}")
    return {
        "message": "Annual license issued",
        "license_key": co.license_key,
        "license_expires": str(co.license_expires),
    }


@app.post("/api/superadmin/companies/{company_id}/suspend")
def suspend_company(
    company_id: int,
    current_user: User = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    co.status = "suspended"
    db.commit()
    return {"message": "Company suspended"}


# ===================== BACKUP / RESTORE =====================
def _company_export_dict(db: Session, company_id: int) -> dict:
    co = db.query(Company).filter(Company.id == company_id).first()
    users = db.query(User).filter(User.company_id == company_id).all()
    coa = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == company_id).all()
    budgets = db.query(BudgetCode).filter(BudgetCode.company_id == company_id).all()
    expenses = db.query(ExpenseCode).filter(ExpenseCode.company_id == company_id).all()
    payments = db.query(PaymentRequest).filter(PaymentRequest.company_id == company_id).all()
    assets = db.query(Asset).filter(Asset.company_id == company_id).all()

    def row(obj, fields):
        return {f: (getattr(obj, f).isoformat() if hasattr(getattr(obj, f), "isoformat") else getattr(obj, f)) for f in fields}

    return {
        "exported_at": datetime.utcnow().isoformat(),
        "company": row(co, ["id", "name", "slug", "address", "status", "license_key", "license_expires",
                            "reporting_currency_code", "reporting_currency_symbol"]),
        "users": [row(u, ["id", "username", "email", "full_name", "role", "is_active"]) for u in users],
        "chart_of_accounts": [row(a, ["code", "name", "account_type"]) for a in coa],
        "budget_codes": [row(b, ["code", "description", "amount", "spent"]) for b in budgets],
        "expense_codes": [row(e, ["code", "description"]) for e in expenses],
        "payment_requests": [row(p, ["request_no", "amount", "status", "narration", "payee_name", "created_at"]) for p in payments],
        "assets": [row(a, ["asset_number", "asset_name", "category", "location", "cost", "condition", "nbv", "image_path"]) for a in assets],
    }


@app.get("/api/backup/company")
def backup_company(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ("company_admin", "superadmin", "finance"):
        raise HTTPException(403, "Not allowed")
    cid = current_user.company_id
    if not cid:
        raise HTTPException(400, "No company context")
    data = _company_export_dict(db, cid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("company_backup.json", json.dumps(data, indent=2, default=str))
        # CSV exports
        for name, rows, headers in [
            ("users.csv", data["users"], ["username", "email", "full_name", "role", "is_active"]),
            ("assets.csv", data["assets"], ["asset_number", "asset_name", "category", "cost", "condition", "nbv"]),
            ("payments.csv", data["payment_requests"], ["request_no", "amount", "status", "payee_name", "created_at"]),
        ]:
            si = io.StringIO()
            w = csv.DictWriter(si, fieldnames=headers, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
            zf.writestr(name, si.getvalue())
    buf.seek(0)
    audit(db, cid, current_user, "BACKUP", "Company backup downloaded")
    fname = f"backup_{data['company']['slug']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.get("/api/superadmin/backup/all")
def backup_all_companies(
    current_user: User = Depends(get_superadmin),
    db: Session = Depends(get_db),
):
    companies = db.query(Company).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for co in companies:
            data = _company_export_dict(db, co.id)
            zf.writestr(f"{co.slug}/company_backup.json", json.dumps(data, indent=2, default=str))
    buf.seek(0)
    audit(db, None, current_user, "BACKUP_ALL", f"{len(companies)} companies")
    fname = f"knowsoft_all_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.post("/api/backup/restore")
async def restore_company_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(get_company_admin),
    db: Session = Depends(get_db),
):
    """Restore non-destructive extras (COA, budgets, expenses, assets) from JSON backup."""
    if not current_user.company_id:
        raise HTTPException(400, "No company context")
    content = await file.read()
    try:
        if file.filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                raw = zf.read("company_backup.json")
        else:
            raw = content
        data = json.loads(raw)
    except Exception as e:
        raise HTTPException(400, f"Invalid backup file: {e}")

    cid = current_user.company_id
    # Import COA
    for row in data.get("chart_of_accounts", []):
        exists = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == cid, ChartOfAccount.code == row["code"]).first()
        if not exists:
            db.add(ChartOfAccount(company_id=cid, code=row["code"], name=row.get("name", ""), account_type=row.get("account_type", "Expense")))
    for row in data.get("budget_codes", []):
        exists = db.query(BudgetCode).filter(BudgetCode.company_id == cid, BudgetCode.code == row["code"]).first()
        if not exists:
            db.add(BudgetCode(company_id=cid, code=row["code"], description=row.get("description", ""), amount=row.get("amount", 0)))
    for row in data.get("assets", []):
        exists = db.query(Asset).filter(Asset.company_id == cid, Asset.asset_number == row["asset_number"]).first()
        if not exists:
            db.add(Asset(
                company_id=cid,
                asset_number=row["asset_number"],
                asset_name=row.get("asset_name", ""),
                category=row.get("category", ""),
                cost=float(row.get("cost") or 0),
                condition=row.get("condition", "Good"),
                nbv=float(row.get("nbv") or 0),
            ))
    db.commit()
    audit(db, cid, current_user, "RESTORE", f"Restored from {file.filename}")
    return {"message": "Backup data restored (merged non-destructively)"}


# ===================== USERS (company scoped) =====================
@app.get("/api/admin/users", response_model=list[UserOut])
def list_users(current_user: User = Depends(get_company_admin), db: Session = Depends(get_db)):
    return db.query(User).filter(User.company_id == current_user.company_id).order_by(User.id).all()


@app.get("/api/admin/approvers")
def list_approvers(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Users who can approve payment requests in this company."""
    return db.query(User).filter(
        User.company_id == current_user.company_id,
        User.is_active == True,
        User.can_approve_payment == True,
    ).all()


@app.post("/api/admin/users", response_model=UserOut)
def create_user(user_in: UserCreate, current_user: User = Depends(get_company_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.company_id == current_user.company_id, User.username == user_in.username).first():
        raise HTTPException(400, "Username already exists in your company")
    role = user_in.role if user_in.role in (
        "company_admin", "finance", "program", "project_manager", "asset_editor", "user"
    ) else "user"
    db_user = User(
        company_id=current_user.company_id,
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        role=role,
        is_active=user_in.is_active,
        can_access_finance=user_in.can_access_finance,
        can_access_inventory=user_in.can_access_inventory,
        can_access_assets=user_in.can_access_assets,
        can_edit_assets=user_in.can_edit_assets or role in ("finance", "project_manager", "asset_editor", "company_admin"),
        can_access_vendors=user_in.can_access_vendors,
        can_access_reports=user_in.can_access_reports,
        can_approve_payment=user_in.can_approve_payment or role in ("finance", "program", "project_manager", "company_admin"),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.put("/api/admin/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, user_in: UserUpdate, current_user: User = Depends(get_company_admin), db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id, User.company_id == current_user.company_id).first()
    if not db_user:
        raise HTTPException(404, "User not found")
    for field, value in user_in.dict(exclude_unset=True).items():
        if field == "password" and value:
            db_user.hashed_password = get_password_hash(value)
        elif field != "password":
            setattr(db_user, field, value)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(get_company_admin), db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id, User.company_id == current_user.company_id).first()
    if not db_user:
        raise HTTPException(404, "User not found")
    if db_user.id == current_user.id:
        raise HTTPException(400, "Cannot delete yourself")
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted"}


# ===================== COMPANY SETTINGS =====================
@app.get("/api/company", response_model=CompanyOut)
def get_company(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not current_user.company_id:
        raise HTTPException(400, "No company")
    return db.query(Company).filter(Company.id == current_user.company_id).first()


@app.put("/api/company", response_model=CompanyOut)
def update_company(data: CompanyUpdate, current_user: User = Depends(get_company_admin), db: Session = Depends(get_db)):
    co = db.query(Company).filter(Company.id == current_user.company_id).first()
    for f, v in data.dict(exclude_unset=True).items():
        setattr(co, f, v)
    db.commit()
    db.refresh(co)
    return co


@app.post("/api/company/upload-logo")
async def upload_logo(file: UploadFile = File(...), current_user: User = Depends(get_company_admin), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(400, "Only image files allowed")
    fname = f"company_{current_user.company_id}_logo{ext}"
    dest = IMAGES_DIR / fname
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    co = db.query(Company).filter(Company.id == current_user.company_id).first()
    co.logo_path = f"/static/images/{fname}"
    db.commit()
    return {"logo_path": co.logo_path}


@app.post("/api/company/upload-favicon")
async def upload_favicon(file: UploadFile = File(...), current_user: User = Depends(get_company_admin), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower() or ".png"
    if ext not in ALLOWED_IMAGE | {".ico"}:
        raise HTTPException(400, "Invalid icon file")
    fname = f"company_{current_user.company_id}_favicon{ext}"
    dest = IMAGES_DIR / fname
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    co = db.query(Company).filter(Company.id == current_user.company_id).first()
    co.favicon_path = f"/static/images/{fname}"
    db.commit()
    return {"favicon_path": co.favicon_path}


@app.get("/api/settings", response_model=CompanySettingsOut)
def public_settings(db: Session = Depends(get_db)):
    s = db.query(CompanySettings).first()
    return s or CompanySettingsOut(org_name="Knowsoft FMSS ERP", logo_path="/static/images/logo.png", favicon_path="/static/images/favicon.ico")


# ===================== FINANCE MASTERS =====================
@app.get("/api/finance/coa")
def list_coa(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return db.query(ChartOfAccount).filter(ChartOfAccount.company_id == current_user.company_id, ChartOfAccount.is_active == True).all()


@app.post("/api/finance/coa")
def create_coa(data: COAIn, current_user: User = Depends(require_roles("finance", "company_admin")), db: Session = Depends(get_db)):
    row = ChartOfAccount(
        company_id=current_user.company_id, code=data.code, name=data.name,
        account_type=data.account_type, project_code=getattr(data, "project_code", "") or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/finance/budget-codes")
def list_budgets(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return db.query(BudgetCode).filter(BudgetCode.company_id == current_user.company_id, BudgetCode.is_active == True).all()


@app.post("/api/finance/budget-codes")
def create_budget(data: BudgetCodeIn, current_user: User = Depends(require_roles("finance", "company_admin")), db: Session = Depends(get_db)):
    row = BudgetCode(
        company_id=current_user.company_id,
        code=data.code,
        description=data.description,
        amount=data.amount,
        default_approver_id=data.default_approver_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/finance/expense-codes")
def list_expenses(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(ExpenseCode).filter(ExpenseCode.company_id == current_user.company_id, ExpenseCode.is_active == True).all()
    result = []
    for e in rows:
        debit = db.query(ChartOfAccount).filter(ChartOfAccount.id == e.default_debit_account_id).first() if e.default_debit_account_id else None
        credit = db.query(ChartOfAccount).filter(ChartOfAccount.id == e.default_credit_account_id).first() if e.default_credit_account_id else None
        result.append({
            "id": e.id, "code": e.code, "description": e.description,
            "budget_code_id": e.budget_code_id,
            "default_debit_account_id": e.default_debit_account_id,
            "default_credit_account_id": e.default_credit_account_id,
            "default_debit_label": f"{debit.code} - {debit.name}" if debit else None,
            "default_credit_label": f"{credit.code} - {credit.name}" if credit else None,
        })
    return result


@app.post("/api/finance/expense-codes")
def create_expense(data: ExpenseCodeIn, current_user: User = Depends(require_roles("finance", "company_admin")), db: Session = Depends(get_db)):
    row = ExpenseCode(
        company_id=current_user.company_id,
        code=data.code,
        description=data.description,
        budget_code_id=data.budget_code_id,
        default_debit_account_id=data.default_debit_account_id,
        default_credit_account_id=data.default_credit_account_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ===================== PAYMENT REQUESTS =====================
def next_request_no(db, company_id):
    n = db.query(PaymentRequest).filter(PaymentRequest.company_id == company_id).count() + 1
    return f"PR-{datetime.utcnow().strftime('%Y%m')}-{n:04d}"


@app.post("/api/payments/request")
def submit_payment_request(
    data: PaymentRequestIn,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    exp = db.query(ExpenseCode).filter(ExpenseCode.id == data.expense_code_id, ExpenseCode.company_id == current_user.company_id).first()
    if not exp:
        raise HTTPException(400, "Invalid expense code")
    bud = db.query(BudgetCode).filter(BudgetCode.id == data.budget_code_id, BudgetCode.company_id == current_user.company_id).first()
    if not bud:
        raise HTTPException(400, "Invalid budget code")
    approver = db.query(User).filter(
        User.id == data.designated_approver_id,
        User.company_id == current_user.company_id,
        User.can_approve_payment == True,
    ).first()
    if not approver:
        raise HTTPException(400, "Select a valid approver for this budget line")

    debit_id = data.debit_account_id or exp.default_debit_account_id
    credit_id = data.credit_account_id or exp.default_credit_account_id

    lines_in = getattr(data, "lines", None) or []
    total_from_lines = 0.0
    for ln in lines_in:
        amt = ln.amount if ln.amount is not None else (float(ln.quantity or 0) * float(ln.unit_cost or 0))
        total_from_lines += amt
    final_amount = total_from_lines if lines_in else float(data.amount)
    if final_amount <= 0:
        raise HTTPException(400, "Amount must be greater than zero (add line items or amount)")

    pr = PaymentRequest(
        company_id=current_user.company_id,
        request_no=next_request_no(db, current_user.company_id),
        requester_id=current_user.id,
        budget_code_id=data.budget_code_id,
        expense_code_id=data.expense_code_id,
        amount=final_amount,
        narration=data.narration,
        payee_name=data.payee_name,
        project_code_id=getattr(data, "project_code_id", None),
        debit_account_id=debit_id,
        credit_account_id=credit_id,
        designated_approver_id=data.designated_approver_id,
        status="submitted",
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    for i, ln in enumerate(lines_in):
        amt = ln.amount if ln.amount is not None else (float(ln.quantity or 0) * float(ln.unit_cost or 0))
        db.add(PaymentLine(
            payment_request_id=pr.id, description=ln.description,
            quantity=float(ln.quantity or 0), unit_cost=float(ln.unit_cost or 0),
            amount=amt, sort_order=i,
        ))
    import json as _json
    db.add(PaymentApprovalLog(
        payment_request_id=pr.id, actor_id=current_user.id, action="submit",
        comment="Submitted", amount_snapshot=pr.amount,
        debit_account_id=debit_id, credit_account_id=credit_id,
        details_json=_json.dumps({
            "request_no": pr.request_no, "payee": pr.payee_name, "amount": pr.amount,
            "budget_code_id": pr.budget_code_id, "expense_code_id": pr.expense_code_id,
            "project_code_id": pr.project_code_id, "by": current_user.username,
        }),
    ))
    audit(db, current_user.company_id, current_user, "PAYMENT_SUBMIT", f"{pr.request_no} amount={pr.amount}")
    db.commit()
    return pr


@app.get("/api/payments")
def list_payments(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    q = db.query(PaymentRequest).filter(PaymentRequest.company_id == current_user.company_id)
    # non-finance/program see own or designated
    if current_user.role not in ("finance", "program", "project_manager", "company_admin", "superadmin"):
        q = q.filter(
            (PaymentRequest.requester_id == current_user.id) |
            (PaymentRequest.designated_approver_id == current_user.id)
        )
    rows = q.order_by(PaymentRequest.created_at.desc()).all()
    out = []
    for p in rows:
        exp = db.query(ExpenseCode).filter(ExpenseCode.id == p.expense_code_id).first()
        bud = db.query(BudgetCode).filter(BudgetCode.id == p.budget_code_id).first()
        proj = db.query(ProjectCode).filter(ProjectCode.id == p.project_code_id).first() if p.project_code_id else None
        out.append({
            "id": p.id, "request_no": p.request_no, "amount": p.amount, "status": p.status,
            "payee_name": p.payee_name, "narration": p.narration,
            "expense_code": exp.code if exp else None,
            "expense_description": exp.description if exp else None,
            "budget_code": bud.code if bud else None,
            "project_code": proj.code if proj else None,
            "project_code_id": p.project_code_id,
            "debit_account_id": p.debit_account_id,
            "credit_account_id": p.credit_account_id,
            "designated_approver_id": p.designated_approver_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return out


@app.post("/api/payments/{pid}/program-approve")
def program_approve(pid: int, data: PaymentAction, current_user: User = Depends(require_roles("program", "project_manager", "company_admin")), db: Session = Depends(get_db)):
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr or pr.status != "submitted":
        raise HTTPException(400, "Request not awaiting program approval")
    if pr.designated_approver_id != current_user.id and current_user.role not in ("company_admin", "project_manager"):
        raise HTTPException(403, "You are not the designated approver for this budget line")
    pr.status = "program_approved"
    pr.program_approved_by = current_user.id
    pr.program_approved_at = datetime.utcnow()
    db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=current_user.id, action="program_approve", comment=data.comment))
    db.commit()
    return {"message": "Program approved", "status": pr.status}


@app.post("/api/payments/{pid}/finance-approve")
def finance_approve(pid: int, data: PaymentAction, current_user: User = Depends(require_roles("finance", "company_admin")), db: Session = Depends(get_db)):
    import json as _json
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr or pr.status != "program_approved":
        raise HTTPException(400, "Request not awaiting finance approval")
    if data.debit_account_id:
        pr.debit_account_id = data.debit_account_id
    if data.credit_account_id:
        pr.credit_account_id = data.credit_account_id
    if not pr.debit_account_id or not pr.credit_account_id:
        raise HTTPException(400, "Finance must select debit and credit accounts from the chart of accounts before approval")
    if not pr.payee_name:
        raise HTTPException(400, "Payee name is required before final finance approval")
    if not pr.budget_code_id or not pr.expense_code_id:
        raise HTTPException(400, "Budget code and expense code are required")
    pr.status = "finance_approved"
    pr.finance_approved_by = current_user.id
    pr.finance_approved_at = datetime.utcnow()
    db.add(PaymentApprovalLog(
        payment_request_id=pr.id, actor_id=current_user.id, action="finance_approve",
        comment=data.comment or "Finance approved with accounts confirmed",
        debit_account_id=pr.debit_account_id, credit_account_id=pr.credit_account_id,
        amount_snapshot=pr.amount,
        details_json=_json.dumps({
            "request_no": pr.request_no, "payee": pr.payee_name, "amount": pr.amount,
            "amount_words": amount_to_words(pr.amount),
            "debit_account_id": pr.debit_account_id, "credit_account_id": pr.credit_account_id,
            "budget_code_id": pr.budget_code_id, "expense_code_id": pr.expense_code_id,
            "project_code_id": pr.project_code_id, "approver": current_user.username,
        }),
    ))
    audit(db, current_user.company_id, current_user, "PAYMENT_FINANCE_APPROVE", f"{pr.request_no} Dr={pr.debit_account_id} Cr={pr.credit_account_id}")
    db.commit()
    return {"message": "Finance approved", "status": pr.status}


@app.post("/api/payments/{pid}/pay")
def mark_paid(pid: int, data: PaymentAction, current_user: User = Depends(require_roles("finance", "company_admin")), db: Session = Depends(get_db)):
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr or pr.status != "finance_approved":
        raise HTTPException(400, "Request not ready for payment")
    if not pr.debit_account_id or not pr.credit_account_id:
        raise HTTPException(400, "Debit and credit accounts required before payment")
    pr.status = "paid"
    pr.paid_at = datetime.utcnow()
    bud = db.query(BudgetCode).filter(BudgetCode.id == pr.budget_code_id).first()
    if bud:
        bud.spent = (bud.spent or 0) + pr.amount
    db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=current_user.id, action="pay", comment=data.comment))
    post_double_entry(
        db, current_user.company_id, current_user.id,
        "payment", pr.id, f"Payment {pr.request_no}", pr.narration or pr.payee_name,
        pr.debit_account_id, pr.credit_account_id, pr.amount,
    )
    db.commit()
    return {"message": "Marked as paid and posted to ledger", "status": pr.status}



@app.post("/api/payments/{pid}/update-accounts")
def update_payment_accounts(
    pid: int,
    debit_account_id: Optional[int] = Form(None),
    credit_account_id: Optional[int] = Form(None),
    budget_code_id: Optional[int] = Form(None),
    expense_code_id: Optional[int] = Form(None),
    project_code_id: Optional[int] = Form(None),
    comment: str = Form(""),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Any reviewing/approving staff (finance, program, admin) can adjust codes before final pay."""
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr:
        raise HTTPException(404, "Not found")
    if pr.status == "paid":
        raise HTTPException(400, "Cannot change accounts on a paid request")
    if debit_account_id is not None:
        pr.debit_account_id = debit_account_id
    if credit_account_id is not None:
        pr.credit_account_id = credit_account_id
    if budget_code_id is not None:
        pr.budget_code_id = budget_code_id
    if expense_code_id is not None:
        pr.expense_code_id = expense_code_id
    if project_code_id is not None:
        pr.project_code_id = project_code_id
    import json as _json
    db.add(PaymentApprovalLog(
        payment_request_id=pr.id, actor_id=current_user.id, action="update_accounts",
        comment=comment or "Accounts/codes adjusted",
        debit_account_id=pr.debit_account_id, credit_account_id=pr.credit_account_id,
        amount_snapshot=pr.amount,
        details_json=_json.dumps({"debit": pr.debit_account_id, "credit": pr.credit_account_id,
                                  "budget": pr.budget_code_id, "expense": pr.expense_code_id}),
    ))
    audit(db, current_user.company_id, current_user, "PAYMENT_CODES_UPDATE", f"{pr.request_no}")
    db.commit()
    return {"message": "Codes updated", "debit_account_id": pr.debit_account_id, "credit_account_id": pr.credit_account_id}


@app.post("/api/payments/{pid}/reject")
def reject_payment(pid: int, data: PaymentAction, current_user: User = Depends(require_roles("finance", "program", "project_manager", "company_admin")), db: Session = Depends(get_db)):
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr:
        raise HTTPException(404, "Not found")
    pr.status = "rejected"
    pr.rejection_reason = data.comment
    db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=current_user.id, action="reject", comment=data.comment))
    db.commit()
    return {"message": "Rejected", "status": pr.status}


@app.get("/api/payments/export")
def export_payments_csv(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(PaymentRequest).filter(PaymentRequest.company_id == current_user.company_id).all()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["Request No", "Amount", "Status", "Payee", "Narration", "Created"])
    for p in rows:
        w.writerow([p.request_no, p.amount, p.status, p.payee_name, p.narration, p.created_at])
    si.seek(0)
    return StreamingResponse(iter([si.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=payments.csv"})


# ===================== ASSETS =====================
def can_edit_assets(user: User) -> bool:
    return user.can_edit_assets or user.role in ("finance", "project_manager", "company_admin", "asset_editor", "superadmin")


def can_view_assets(user: User) -> bool:
    return user.can_access_assets or can_edit_assets(user)


@app.get("/api/assets")
def list_assets(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not can_view_assets(current_user):
        raise HTTPException(403, "No access to assets")
    return db.query(Asset).filter(Asset.company_id == current_user.company_id).order_by(Asset.id.desc()).all()


@app.post("/api/assets")
def create_asset(data: AssetIn, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not can_edit_assets(current_user):
        raise HTTPException(403, "Only designated staff, finance, or project manager can edit the asset register")
    a = Asset(company_id=current_user.company_id, created_by=current_user.id, **data.dict())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, data: AssetIn, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not can_edit_assets(current_user):
        raise HTTPException(403, "Not allowed to edit assets")
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.company_id == current_user.company_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    for f, v in data.dict().items():
        setattr(a, f, v)
    db.commit()
    db.refresh(a)
    return a


@app.post("/api/assets/{asset_id}/photo")
async def upload_asset_photo(
    asset_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not can_edit_assets(current_user):
        raise HTTPException(403, "Not allowed")
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.company_id == current_user.company_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(400, "Only image files allowed")
    # size limit ~5MB
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 5MB)")
    fname = f"asset_{current_user.company_id}_{asset_id}{ext}"
    dest = UPLOADS_DIR / fname
    dest.write_bytes(content)
    a.image_path = f"/static/uploads/{fname}"
    db.commit()
    return {"image_path": a.image_path}


@app.get("/api/assets/export")
def export_assets_csv(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not can_view_assets(current_user):
        raise HTTPException(403, "No access")
    rows = db.query(Asset).filter(Asset.company_id == current_user.company_id).all()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["Asset Number", "Name", "Category", "Location", "Cost", "NBV", "Condition", "Insurance"])
    for a in rows:
        w.writerow([a.asset_number, a.asset_name, a.category, a.location, a.cost, a.nbv, a.condition, a.insurance])
    si.seek(0)
    return StreamingResponse(iter([si.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=assets.csv"})


@app.get("/api/dashboard/stats")
def dashboard_stats(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    cid = current_user.company_id
    if not cid:
        # superadmin overview
        return {
            "companies_pending": db.query(Company).filter(Company.status == "pending").count(),
            "companies_approved": db.query(Company).filter(Company.status == "approved").count(),
            "companies_total": db.query(Company).count(),
        }
    assets = db.query(Asset).filter(Asset.company_id == cid).all()
    payments = db.query(PaymentRequest).filter(PaymentRequest.company_id == cid).all()
    return {
        "assets_count": len(assets),
        "assets_value": sum(a.nbv or a.cost or 0 for a in assets),
        "payments_pending": sum(1 for p in payments if p.status in ("submitted", "program_approved")),
        "payments_paid": sum(1 for p in payments if p.status == "paid"),
        "payments_total_amount": sum(p.amount for p in payments if p.status == "paid"),
        "users_count": db.query(User).filter(User.company_id == cid).count(),
        "condition_breakdown": {
            "Good": sum(1 for a in assets if (a.condition or "").lower() == "good"),
            "Fair": sum(1 for a in assets if (a.condition or "").lower() == "fair"),
            "Bad": sum(1 for a in assets if (a.condition or "").lower() == "bad"),
            "Lost": sum(1 for a in assets if (a.condition or "").lower() == "lost"),
        },
        "payment_status_breakdown": {
            "submitted": sum(1 for p in payments if p.status == "submitted"),
            "program_approved": sum(1 for p in payments if p.status == "program_approved"),
            "finance_approved": sum(1 for p in payments if p.status == "finance_approved"),
            "paid": sum(1 for p in payments if p.status == "paid"),
            "rejected": sum(1 for p in payments if p.status == "rejected"),
        },
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.2.0", "multi_tenant": True, "licensing": True}



# ===================== HELPERS: JOURNAL POSTING =====================
def next_entry_no(db, company_id, prefix="JE"):
    n = db.query(JournalEntry).filter(JournalEntry.company_id == company_id).count() + 1
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m')}-{n:05d}"


def post_double_entry(db, company_id, user_id, source_type, source_id, description, narration,
                      debit_account_id, credit_account_id, amount, project_code_id=None, entry_date=None):
    """Post balanced debit/credit lines to the general ledger."""
    if not debit_account_id or not credit_account_id:
        raise HTTPException(400, "Debit and credit accounts are required")
    if amount is None or float(amount) == 0:
        raise HTTPException(400, "Amount must be non-zero")
    amt = abs(float(amount))
    entry_no = next_entry_no(db, company_id)
    ed = entry_date or date.today()
    db.add(JournalEntry(
        company_id=company_id, entry_no=entry_no, entry_date=ed,
        source_type=source_type, source_id=source_id,
        account_id=debit_account_id, project_code_id=project_code_id,
        description=description, narration=narration,
        debit=amt, credit=0.0, created_by=user_id,
    ))
    db.add(JournalEntry(
        company_id=company_id, entry_no=entry_no, entry_date=ed,
        source_type=source_type, source_id=source_id,
        account_id=credit_account_id, project_code_id=project_code_id,
        description=description, narration=narration,
        debit=0.0, credit=amt, created_by=user_id,
    ))
    return entry_no


def cleanup_disposed_assets(db: Session):
    """Delete assets disposed more than 14 days ago."""
    cutoff = datetime.utcnow() - timedelta(days=14)
    old = db.query(Asset).filter(
        Asset.status == "disposed",
        Asset.disposed_at != None,
        Asset.disposed_at < cutoff,
    ).all()
    for a in old:
        db.delete(a)
    if old:
        db.commit()
        print(f"🧹 Removed {len(old)} disposed assets older than 14 days")


# ===================== PAYMENT DETAIL + ATTACHMENTS (<=100KB) =====================
MAX_ATTACH = 100 * 1024  # 100 KB


@app.get("/api/payments/{pid}")
def get_payment_detail(pid: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr:
        raise HTTPException(404, "Payment request not found")
    exp = db.query(ExpenseCode).filter(ExpenseCode.id == pr.expense_code_id).first()
    bud = db.query(BudgetCode).filter(BudgetCode.id == pr.budget_code_id).first()
    debit = db.query(ChartOfAccount).filter(ChartOfAccount.id == pr.debit_account_id).first() if pr.debit_account_id else None
    credit = db.query(ChartOfAccount).filter(ChartOfAccount.id == pr.credit_account_id).first() if pr.credit_account_id else None
    requester = db.query(User).filter(User.id == pr.requester_id).first()
    approver = db.query(User).filter(User.id == pr.designated_approver_id).first()
    proj = db.query(ProjectCode).filter(ProjectCode.id == pr.project_code_id).first() if pr.project_code_id else None
    atts = db.query(PaymentAttachment).filter(PaymentAttachment.payment_request_id == pr.id).all()
    logs = db.query(PaymentApprovalLog).filter(PaymentApprovalLog.payment_request_id == pr.id).order_by(PaymentApprovalLog.created_at).all()
    pay_lines = db.query(PaymentLine).filter(PaymentLine.payment_request_id == pr.id).order_by(PaymentLine.sort_order).all()
    coa = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == current_user.company_id, ChartOfAccount.is_active == True).all()
    hist = []
    for l in logs:
        actor = db.query(User).filter(User.id == l.actor_id).first()
        hist.append({
            "action": l.action, "comment": l.comment,
            "actor": (actor.full_name or actor.username) if actor else str(l.actor_id),
            "actor_id": l.actor_id,
            "debit_account_id": l.debit_account_id, "credit_account_id": l.credit_account_id,
            "amount_snapshot": l.amount_snapshot, "details_json": l.details_json,
            "at": l.created_at.isoformat() if l.created_at else None,
        })
    return {
        "id": pr.id, "request_no": pr.request_no, "amount": pr.amount, "status": pr.status,
        "payee_name": pr.payee_name, "narration": pr.narration, "currency": pr.currency,
        "amount_in_words": amount_to_words(pr.amount),
        "budget_code_id": pr.budget_code_id,
        "budget_code": bud.code if bud else None, "budget_description": bud.description if bud else None,
        "expense_code_id": pr.expense_code_id,
        "expense_code": exp.code if exp else None, "expense_description": exp.description if exp else None,
        "project_code_id": pr.project_code_id,
        "project_code": proj.code if proj else None, "project_name": proj.name if proj else None,
        "debit_account": f"{debit.code} - {debit.name}" if debit else None,
        "credit_account": f"{credit.code} - {credit.name}" if credit else None,
        "debit_account_id": pr.debit_account_id, "credit_account_id": pr.credit_account_id,
        "requester": requester.full_name or requester.username if requester else None,
        "designated_approver": approver.full_name or approver.username if approver else None,
        "rejection_reason": pr.rejection_reason,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "program_approved_at": pr.program_approved_at.isoformat() if pr.program_approved_at else None,
        "finance_approved_at": pr.finance_approved_at.isoformat() if pr.finance_approved_at else None,
        "paid_at": pr.paid_at.isoformat() if pr.paid_at else None,
        "lines": [{"id": L.id, "description": L.description, "quantity": L.quantity, "unit_cost": L.unit_cost, "amount": L.amount} for L in pay_lines],
        "attachments": [{"id": a.id, "filename": a.filename, "size_bytes": a.size_bytes, "url": a.stored_path} for a in atts],
        "history": hist,
        "chart_of_accounts": [{"id": a.id, "code": a.code, "name": a.name, "account_type": a.account_type, "label": f"{a.code} - {a.name}"} for a in coa],
        "can_edit_accounts": current_user.role in ("finance", "company_admin", "superadmin", "program", "project_manager") or current_user.can_approve_payment,
        "budget_amount": float(bud.amount or 0) if bud else 0,
        "budget_spent": float(bud.spent or 0) if bud else 0,
        "budget_available": float((bud.amount or 0) - (bud.spent or 0)) if bud else 0,
        "funds_sufficient": (float((bud.amount or 0) - (bud.spent or 0)) >= float(pr.amount or 0)) if bud else True,
    }


@app.post("/api/payments/{pid}/attachments")
async def upload_payment_attachment(
    pid: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr:
        raise HTTPException(404, "Not found")
    content = await file.read()
    if len(content) > MAX_ATTACH:
        raise HTTPException(400, f"Attachment must be ≤ 100KB (got {len(content)} bytes)")
    ext = Path(file.filename or "file").suffix.lower()
    if ext not in {".pdf", ".png", ".jpg", ".jpeg", ".csv", ".xlsx", ".doc", ".docx", ".txt"}:
        raise HTTPException(400, "File type not allowed")
    safe = f"pay_{current_user.company_id}_{pid}_{secrets.token_hex(4)}{ext}"
    dest = UPLOADS_DIR / safe
    dest.write_bytes(content)
    att = PaymentAttachment(
        payment_request_id=pr.id,
        filename=file.filename or safe,
        stored_path=f"/static/uploads/{safe}",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        uploaded_by=current_user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return {"id": att.id, "filename": att.filename, "url": att.stored_path, "size_bytes": att.size_bytes}


# When marking paid, post to ledger
_orig_mark = None  # we patch mark_paid below by replacing function body via string if needed

# ===================== PROJECT CODES =====================
@app.get("/api/finance/projects")
def list_projects(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return db.query(ProjectCode).filter(ProjectCode.company_id == current_user.company_id, ProjectCode.is_active == True).all()


@app.post("/api/finance/projects")
def create_project(
    code: str = Form(...), name: str = Form(...), description: str = Form(""),
    current_user: User = Depends(require_roles("finance", "company_admin")),
    db: Session = Depends(get_db),
):
    row = ProjectCode(company_id=current_user.company_id, code=code, name=name, description=description)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ===================== LEDGER / TRIAL BALANCE / REPORTS =====================
@app.get("/api/reports/ledger")
def general_ledger(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not (current_user.can_access_reports or current_user.role in ("finance", "company_admin", "superadmin")):
        raise HTTPException(403, "No report access")
    rows = db.query(JournalEntry).filter(JournalEntry.company_id == current_user.company_id).order_by(JournalEntry.entry_date, JournalEntry.id).all()
    out = []
    for j in rows:
        acc = db.query(ChartOfAccount).filter(ChartOfAccount.id == j.account_id).first()
        out.append({
            "entry_no": j.entry_no, "date": str(j.entry_date), "source_type": j.source_type,
            "account": f"{acc.code} - {acc.name}" if acc else str(j.account_id),
            "description": j.description, "narration": j.narration,
            "debit": j.debit, "credit": j.credit,
        })
    return out


@app.get("/api/reports/trial-balance")
def trial_balance(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not (current_user.can_access_reports or current_user.role in ("finance", "company_admin", "superadmin")):
        raise HTTPException(403, "No report access")
    accounts = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == current_user.company_id).all()
    result = []
    total_d = total_c = 0.0
    for acc in accounts:
        lines = db.query(JournalEntry).filter(JournalEntry.company_id == current_user.company_id, JournalEntry.account_id == acc.id).all()
        d = sum(l.debit or 0 for l in lines)
        c = sum(l.credit or 0 for l in lines)
        if d == 0 and c == 0:
            continue
        total_d += d
        total_c += c
        result.append({
            "code": acc.code, "name": acc.name, "type": acc.account_type,
            "project_code": acc.project_code or "",
            "debit": d, "credit": c, "balance": d - c,
        })
    return {"rows": result, "total_debit": total_d, "total_credit": total_c, "balanced": abs(total_d - total_c) < 0.01}


@app.get("/api/reports/ledger/export")
def export_ledger_csv(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    data = general_ledger(current_user, db)
    si = io.StringIO()
    w = csv.DictWriter(si, fieldnames=["entry_no", "date", "source_type", "account", "description", "narration", "debit", "credit"])
    w.writeheader()
    for r in data:
        w.writerow(r)
    si.seek(0)
    return StreamingResponse(iter([si.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=general_ledger.csv"})


@app.get("/api/reports/trial-balance/export")
def export_tb_csv(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    data = trial_balance(current_user, db)
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["Code", "Name", "Type", "Project", "Debit", "Credit", "Balance"])
    for r in data["rows"]:
        w.writerow([r["code"], r["name"], r["type"], r["project_code"], r["debit"], r["credit"], r["balance"]])
    w.writerow([])
    w.writerow(["TOTAL", "", "", "", data["total_debit"], data["total_credit"], ""])
    si.seek(0)
    return StreamingResponse(iter([si.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=trial_balance.csv"})


# ===================== ASSET DETAIL + ACCOUNTING + DISPOSE =====================
@app.get("/api/assets/dashboard")
def assets_dashboard(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not can_view_assets(current_user):
        raise HTTPException(403, "No access")
    assets = db.query(Asset).filter(Asset.company_id == current_user.company_id, Asset.status != "disposed").all()
    # also include disposed for stats? exclude from main lists
    all_a = db.query(Asset).filter(Asset.company_id == current_user.company_id).all()
    insured = sum(1 for a in assets if (a.insurance or "").lower() in ("yes", "y", "true", "insured"))
    return {
        "total": len(assets),
        "insured": insured,
        "uninsured": len(assets) - insured,
        "damaged": sum(1 for a in assets if (a.condition or "").lower() in ("bad", "damaged")),
        "under_repair": sum(1 for a in assets if (a.status or "").lower() == "under_repair"),
        "disposed": sum(1 for a in all_a if (a.status or "").lower() == "disposed"),
        "total_cost": sum(a.cost or 0 for a in assets),
        "total_nbv": sum(a.nbv or 0 for a in assets),
        "by_condition": {
            "Good": sum(1 for a in assets if (a.condition or "").lower() == "good"),
            "Fair": sum(1 for a in assets if (a.condition or "").lower() == "fair"),
            "Bad": sum(1 for a in assets if (a.condition or "").lower() in ("bad", "damaged")),
            "Lost": sum(1 for a in assets if (a.condition or "").lower() == "lost"),
        },
        "useful_life_buckets": {
            "0-2 yrs": sum(1 for a in assets if (a.useful_life or 0) <= 2),
            "3-5 yrs": sum(1 for a in assets if 2 < (a.useful_life or 0) <= 5),
            "6-10 yrs": sum(1 for a in assets if 5 < (a.useful_life or 0) <= 10),
            "10+ yrs": sum(1 for a in assets if (a.useful_life or 0) > 10),
        },
    }


@app.get("/api/assets/{asset_id}")
def get_asset(asset_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not can_view_assets(current_user):
        raise HTTPException(403, "No access")
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.company_id == current_user.company_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    entries = db.query(AssetAccountingEntry).filter(AssetAccountingEntry.asset_id == a.id).order_by(AssetAccountingEntry.created_at.desc()).all()
    debit = db.query(ChartOfAccount).filter(ChartOfAccount.id == a.debit_account_id).first() if a.debit_account_id else None
    credit = db.query(ChartOfAccount).filter(ChartOfAccount.id == a.credit_account_id).first() if a.credit_account_id else None
    return {
        **{c.name: getattr(a, c.name) for c in a.__table__.columns},
        "debit_account_label": f"{debit.code} - {debit.name}" if debit else None,
        "credit_account_label": f"{credit.code} - {credit.name}" if credit else None,
        "accounting_entries": [{
            "id": e.id, "date": str(e.entry_date), "description": e.description,
            "narration": e.narration, "amount": e.amount, "journal_entry_no": e.journal_entry_no,
        } for e in entries],
    }


@app.post("/api/assets/{asset_id}/accounting")
def post_asset_accounting(
    asset_id: int,
    amount: float = Form(...),
    description: str = Form(...),
    narration: str = Form(""),
    debit_account_id: int = Form(...),
    credit_account_id: int = Form(...),
    project_code_id: Optional[int] = Form(None),
    current_user: User = Depends(require_roles("finance", "company_admin", "project_manager")),
    db: Session = Depends(get_db),
):
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.company_id == current_user.company_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    entry_no = post_double_entry(
        db, current_user.company_id, current_user.id,
        "asset_adjustment", a.id, description, narration,
        debit_account_id, credit_account_id, amount, project_code_id,
    )
    a.nbv = (a.nbv or 0) + float(amount)
    db.add(AssetAccountingEntry(
        company_id=current_user.company_id, asset_id=a.id,
        description=description, narration=narration, amount=float(amount),
        debit_account_id=debit_account_id, credit_account_id=credit_account_id,
        project_code_id=project_code_id, journal_entry_no=entry_no, created_by=current_user.id,
    ))
    db.commit()
    return {"message": "Accounting entry posted", "journal_entry_no": entry_no, "new_nbv": a.nbv}


@app.post("/api/assets/{asset_id}/dispose")
def dispose_asset(asset_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not can_edit_assets(current_user):
        raise HTTPException(403, "Not allowed")
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.company_id == current_user.company_id).first()
    if not a:
        raise HTTPException(404, "Not found")
    a.status = "disposed"
    a.disposed_at = datetime.utcnow()
    a.condition = "Disposed"
    db.commit()
    return {"message": "Asset marked disposed. It will be auto-deleted after 14 days."}


# On asset create, optional initial capitalization journal if accounts provided
# (handled in frontend + optional extend create_asset)

# ===================== INVENTORY =====================
@app.get("/api/inventory")
def list_inventory(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not (current_user.can_access_inventory or current_user.role in ("finance", "company_admin", "superadmin")):
        raise HTTPException(403, "No inventory access")
    return db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id).order_by(InventoryItem.id.desc()).all()


@app.post("/api/inventory")
def create_inventory(
    item_code: str = Form(...), item_name: str = Form(...), category: str = Form(""),
    department: str = Form(""), cost_price: float = Form(0), qty_received: float = Form(0),
    note: str = Form(""), receive_method: str = Form(""), funding_source: str = Form(""),
    debit_account_id: Optional[int] = Form(None), credit_account_id: Optional[int] = Form(None),
    project_code_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
):
    if not (current_user.can_access_inventory or current_user.role in ("finance", "company_admin")):
        raise HTTPException(403, "No access")
    bal = float(qty_received)
    total = bal * float(cost_price)
    item = InventoryItem(
        company_id=current_user.company_id, item_code=item_code, item_name=item_name,
        category=category, department=department, cost_price=cost_price,
        qty_received=bal, qty_issued=0, balance_qty=bal, total_value=total,
        note=note, receive_method=receive_method, funding_source=funding_source,
        debit_account_id=debit_account_id, credit_account_id=credit_account_id,
        project_code_id=project_code_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    if debit_account_id and credit_account_id and total > 0:
        post_double_entry(
            db, current_user.company_id, current_user.id,
            "inventory", item.id, f"Stock receive {item_code}", note or item_name,
            debit_account_id, credit_account_id, total, project_code_id,
        )
        db.commit()
    return item


@app.post("/api/inventory/{item_id}/move")
def inventory_move(
    item_id: int,
    movement_type: str = Form(...),  # receive | issue
    quantity: float = Form(...),
    unit_cost: float = Form(0),
    narration: str = Form(""),
    debit_account_id: Optional[int] = Form(None),
    credit_account_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    qty = float(quantity)
    cost = float(unit_cost) or (item.cost_price or 0)
    total = qty * cost
    if movement_type == "receive":
        item.qty_received = (item.qty_received or 0) + qty
        item.balance_qty = (item.balance_qty or 0) + qty
    elif movement_type == "issue":
        if qty > (item.balance_qty or 0):
            raise HTTPException(400, "Insufficient stock")
        item.qty_issued = (item.qty_issued or 0) + qty
        item.balance_qty = (item.balance_qty or 0) - qty
    else:
        raise HTTPException(400, "movement_type must be receive or issue")
    item.total_value = (item.balance_qty or 0) * (item.cost_price or cost)
    item.last_updated = datetime.utcnow()
    debit = debit_account_id or item.debit_account_id
    credit = credit_account_id or item.credit_account_id
    db.add(InventoryMovement(
        company_id=current_user.company_id, item_id=item.id, movement_type=movement_type,
        quantity=qty, unit_cost=cost, total=total, narration=narration,
        debit_account_id=debit, credit_account_id=credit, created_by=current_user.id,
    ))
    if debit and credit and total > 0:
        # issue: expense/COGS debit, inventory credit; receive: inventory debit, cash/AP credit
        if movement_type == "issue":
            post_double_entry(db, current_user.company_id, current_user.id, "inventory", item.id,
                              f"Issue {item.item_code}", narration, debit, credit, total)
        else:
            post_double_entry(db, current_user.company_id, current_user.id, "inventory", item.id,
                              f"Receive {item.item_code}", narration, debit, credit, total)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/inventory/export")
def export_inventory(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id).all()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["Item Code", "Name", "Category", "Department", "Cost", "Received", "Issued", "Balance", "Total Value"])
    for i in rows:
        w.writerow([i.item_code, i.item_name, i.category, i.department, i.cost_price, i.qty_received, i.qty_issued, i.balance_qty, i.total_value])
    si.seek(0)
    return StreamingResponse(iter([si.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=inventory.csv"})


# ===================== VENDORS =====================
@app.get("/api/vendors")
def list_vendors(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not (current_user.can_access_vendors or current_user.role in ("finance", "company_admin", "superadmin")):
        raise HTTPException(403, "No vendor access")
    return db.query(Vendor).filter(Vendor.company_id == current_user.company_id).order_by(Vendor.id.desc()).all()


@app.post("/api/vendors")
def create_vendor(
    vendor_number: str = Form(...), name: str = Form(...), address: str = Form(""),
    cac_number: str = Form(""), experience: str = Form(""), tax_clearance: str = Form(""),
    bank: str = Form(""), reg_with_govt: str = Form(""), audit_3yrs: str = Form(""),
    description: str = Form(""), amount: float = Form(0),
    debit_account_id: Optional[int] = Form(None), credit_account_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
):
    if not (current_user.can_access_vendors or current_user.role in ("finance", "company_admin")):
        raise HTTPException(403, "No access")
    # simple score like original analyze
    score = 0
    if tax_clearance.lower() in ("yes", "y"): score += 25
    if reg_with_govt.lower() in ("yes", "y"): score += 25
    if audit_3yrs.lower() in ("yes", "y"): score += 25
    if experience: score += min(25, len(experience))
    v = Vendor(
        company_id=current_user.company_id, vendor_number=vendor_number, name=name,
        address=address, cac_number=cac_number, experience=experience, tax_clearance=tax_clearance,
        bank=bank, reg_with_govt=reg_with_govt, audit_3yrs=audit_3yrs, description=description,
        amount=amount, score=score, debit_account_id=debit_account_id, credit_account_id=credit_account_id,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    if debit_account_id and credit_account_id and amount > 0:
        post_double_entry(
            db, current_user.company_id, current_user.id, "vendor", v.id,
            f"Vendor commitment {name}", description or name,
            debit_account_id, credit_account_id, amount,
        )
        db.commit()
    return v


@app.get("/api/vendors/export")
def export_vendors(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(Vendor).filter(Vendor.company_id == current_user.company_id).all()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["Vendor No", "Name", "CAC", "Tax Clearance", "Bank", "Amount", "Score", "Description"])
    for v in rows:
        w.writerow([v.vendor_number, v.name, v.cac_number, v.tax_clearance, v.bank, v.amount, v.score, v.description])
    si.seek(0)
    return StreamingResponse(iter([si.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=vendors.csv"})


# Patch mark_paid to post journal



@app.post("/api/finance/journal")
def post_manual_journal(
    description: str = Form(...),
    narration: str = Form(""),
    debit_account_id: int = Form(...),
    credit_account_id: int = Form(...),
    amount: float = Form(...),
    project_code_id: Optional[int] = Form(None),
    current_user: User = Depends(require_roles("finance", "company_admin")),
    db: Session = Depends(get_db),
):
    entry_no = post_double_entry(
        db, current_user.company_id, current_user.id,
        "manual", None, description, narration,
        debit_account_id, credit_account_id, amount, project_code_id,
    )
    db.commit()
    return {"message": "Journal posted", "entry_no": entry_no}


@app.get("/api/finance/bank-lines")
def bank_cash_lines(current_user: User = Depends(require_roles("finance", "company_admin")), db: Session = Depends(get_db)):
    """Ledger lines for Cash-type accounts for reconciliation."""
    cash_ids = [a.id for a in db.query(ChartOfAccount).filter(
        ChartOfAccount.company_id == current_user.company_id,
        ChartOfAccount.account_type == "Cash",
    ).all()]
    if not cash_ids:
        return []
    rows = db.query(JournalEntry).filter(
        JournalEntry.company_id == current_user.company_id,
        JournalEntry.account_id.in_(cash_ids),
    ).order_by(JournalEntry.entry_date.desc()).limit(200).all()
    out = []
    for j in rows:
        acc = db.query(ChartOfAccount).filter(ChartOfAccount.id == j.account_id).first()
        out.append({
            "id": j.id, "entry_no": j.entry_no, "date": str(j.entry_date),
            "account": f"{acc.code} - {acc.name}" if acc else "",
            "description": j.description, "debit": j.debit, "credit": j.credit,
            "narration": j.narration,
        })
    return out




# ===================== BANK RECONCILIATION (full) =====================
@app.get("/api/finance/bank-recon")
def bank_recon_lines(
    account_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(require_roles("finance", "company_admin")),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    q_acc = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == cid, ChartOfAccount.account_type == "Cash")
    cash_accounts = q_acc.all()
    cash_ids = [a.id for a in cash_accounts]
    if account_id:
        cash_ids = [account_id] if account_id in cash_ids or True else cash_ids

    q = db.query(JournalEntry).filter(JournalEntry.company_id == cid, JournalEntry.account_id.in_(cash_ids) if cash_ids else False)
    if start_date:
        try:
            q = q.filter(JournalEntry.entry_date >= date.fromisoformat(start_date))
        except Exception:
            pass
    if end_date:
        try:
            q = q.filter(JournalEntry.entry_date <= date.fromisoformat(end_date))
        except Exception:
            pass
    rows = q.order_by(JournalEntry.entry_date, JournalEntry.id).all()

    running = 0.0
    out = []
    reconciled_total = 0.0
    outstanding_total = 0.0
    for j in rows:
        running += (j.debit or 0) - (j.credit or 0)
        st = db.query(BankReconState).filter(
            BankReconState.company_id == cid, BankReconState.journal_entry_id == j.id
        ).first()
        ticked = bool(st and st.ticked)
        net = (j.debit or 0) - (j.credit or 0)
        if ticked:
            reconciled_total += abs(net)
        else:
            outstanding_total += abs(net)
        acc = db.query(ChartOfAccount).filter(ChartOfAccount.id == j.account_id).first()
        out.append({
            "journal_entry_id": j.id,
            "entry_no": j.entry_no,
            "date": str(j.entry_date),
            "account_id": j.account_id,
            "account": f"{acc.code} - {acc.name}" if acc else "",
            "description": j.description,
            "narration": j.narration,
            "debit": j.debit,
            "credit": j.credit,
            "balance": running,
            "ticked": ticked,
            "source_type": j.source_type,
            "source_id": j.source_id,
        })
    return {
        "lines": out,
        "cash_accounts": [{"id": a.id, "code": a.code, "name": a.name} for a in cash_accounts],
        "totals": {
            "reconciled": reconciled_total,
            "outstanding": outstanding_total,
            "book_balance": running,
        },
    }


@app.post("/api/finance/bank-recon/tick")
def bank_recon_tick(
    journal_entry_id: int = Form(...),
    ticked: bool = Form(True),
    note: str = Form(""),
    current_user: User = Depends(require_roles("finance", "company_admin")),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    je = db.query(JournalEntry).filter(JournalEntry.id == journal_entry_id, JournalEntry.company_id == cid).first()
    if not je:
        raise HTTPException(404, "Journal line not found")
    st = db.query(BankReconState).filter(
        BankReconState.company_id == cid, BankReconState.journal_entry_id == journal_entry_id
    ).first()
    if not st:
        st = BankReconState(company_id=cid, journal_entry_id=journal_entry_id)
        db.add(st)
    st.ticked = ticked
    st.ticked_by = current_user.id
    st.ticked_at = datetime.utcnow() if ticked else None
    st.note = note
    db.commit()
    return {"ok": True, "ticked": st.ticked}


@app.post("/api/finance/bank-recon/session")
def save_bank_session(
    account_id: int = Form(...),
    statement_balance: float = Form(0),
    book_balance: float = Form(0),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    current_user: User = Depends(require_roles("finance", "company_admin")),
    db: Session = Depends(get_db),
):
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    sess = BankStatementSession(
        company_id=current_user.company_id, account_id=account_id,
        start_date=sd, end_date=ed, statement_balance=statement_balance,
        book_balance=book_balance, created_by=current_user.id,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


@app.get("/api/finance/transaction-trail/{journal_entry_id}")
def transaction_trail(
    journal_entry_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Follow a ledger line back to its source document."""
    j = db.query(JournalEntry).filter(
        JournalEntry.id == journal_entry_id, JournalEntry.company_id == current_user.company_id
    ).first()
    if not j:
        raise HTTPException(404, "Not found")
    # paired lines same entry_no
    pair = db.query(JournalEntry).filter(
        JournalEntry.company_id == current_user.company_id, JournalEntry.entry_no == j.entry_no
    ).all()
    source = None
    if j.source_type == "payment" and j.source_id:
        pr = db.query(PaymentRequest).filter(PaymentRequest.id == j.source_id).first()
        if pr:
            source = {"type": "payment", "id": pr.id, "ref": pr.request_no, "payee": pr.payee_name, "amount": pr.amount, "status": pr.status}
    elif j.source_type == "inventory" and j.source_id:
        inv = db.query(InventoryItem).filter(InventoryItem.id == j.source_id).first()
        if inv:
            source = {"type": "inventory", "id": inv.id, "ref": inv.item_code, "name": inv.item_name}
    elif j.source_type == "asset_adjustment" and j.source_id:
        a = db.query(Asset).filter(Asset.id == j.source_id).first()
        if a:
            source = {"type": "asset", "id": a.id, "ref": a.asset_number, "name": a.asset_name}
    elif j.source_type == "vendor" and j.source_id:
        v = db.query(Vendor).filter(Vendor.id == j.source_id).first()
        if v:
            source = {"type": "vendor", "id": v.id, "ref": v.vendor_number, "name": v.name}
    creator = db.query(User).filter(User.id == j.created_by).first() if j.created_by else None
    return {
        "line": {
            "id": j.id, "entry_no": j.entry_no, "date": str(j.entry_date),
            "description": j.description, "narration": j.narration,
            "debit": j.debit, "credit": j.credit, "source_type": j.source_type, "source_id": j.source_id,
        },
        "paired_entries": [{
            "id": p.id, "account_id": p.account_id, "debit": p.debit, "credit": p.credit, "description": p.description
        } for p in pair],
        "source": source,
        "created_by": (creator.full_name or creator.username) if creator else None,
        "can_correct": current_user.role in ("finance", "company_admin", "superadmin"),
    }


@app.post("/api/finance/correction-request")
def create_correction_request(
    to_user_id: int = Form(...),
    message: str = Form(...),
    journal_entry_id: Optional[int] = Form(None),
    source_type: str = Form(""),
    source_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = CorrectionRequest(
        company_id=current_user.company_id,
        journal_entry_id=journal_entry_id,
        source_type=source_type,
        source_id=source_id,
        from_user_id=current_user.id,
        to_user_id=to_user_id,
        message=message,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"message": "Correction request sent", "id": row.id}


@app.get("/api/finance/correction-requests")
def list_corrections(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return db.query(CorrectionRequest).filter(
        CorrectionRequest.company_id == current_user.company_id,
        (CorrectionRequest.to_user_id == current_user.id) | (CorrectionRequest.from_user_id == current_user.id),
    ).order_by(CorrectionRequest.created_at.desc()).limit(100).all()


# ===================== BUDGET VARIANCE (per project) =====================
@app.get("/api/reports/budget-variance")
def budget_variance(
    project_code: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    budgets = db.query(BudgetCode).filter(BudgetCode.company_id == cid, BudgetCode.is_active == True).all()
    # actuals from payment requests paid + journal on expense accounts linked via expense codes
    rows = []
    total_b = total_a = 0.0
    for b in budgets:
        # filter by project if budget description/code contains project or via expense link
        if project_code and project_code.lower() not in (b.code or "").lower() and project_code.lower() not in (b.description or "").lower():
            # also check project codes table match
            pass  # still include if no strict link — filter loosely
            if project_code and project_code not in (b.code or "") and project_code not in (b.description or ""):
                continue
        actual = float(b.spent or 0)
        # also sum paid payments on this budget
        pays = db.query(PaymentRequest).filter(
            PaymentRequest.company_id == cid,
            PaymentRequest.budget_code_id == b.id,
            PaymentRequest.status == "paid",
        ).all()
        actual = max(actual, sum(p.amount for p in pays))
        budgeted = float(b.amount or 0)
        var = budgeted - actual
        rows.append({
            "budget_code": b.code,
            "description": b.description,
            "budgeted": budgeted,
            "actual": actual,
            "variance": var,
            "remark": "Favourable" if var >= 0 else "Adverse",
        })
        total_b += budgeted
        total_a += actual
    return {
        "project_code": project_code or "ALL",
        "rows": rows,
        "total_budget": total_b,
        "total_actual": total_a,
        "total_variance": total_b - total_a,
    }


# ===================== PDF / EXCEL REPORTS =====================
from reports import build_pdf, build_csv


def _company_and_currency(db, user):
    co = db.query(Company).filter(Company.id == user.company_id).first() if user.company_id else None
    code = co.reporting_currency_code if co else "NGN"
    sym = co.reporting_currency_symbol if co else "₦"
    return co, code, sym


@app.get("/api/reports/bank-recon/pdf")
def bank_recon_pdf(
    account_id: Optional[int] = None,
    current_user: User = Depends(require_roles("finance", "company_admin")),
    db: Session = Depends(get_db),
):
    data = bank_recon_lines(account_id, None, None, current_user, db)
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Tick", "Date", "Entry", "Account", "Description", f"Debit ({sym})", f"Credit ({sym})", "Balance"]
    rows = []
    for L in data["lines"]:
        rows.append([
            "✓" if L["ticked"] else "",
            L["date"], L["entry_no"], L["account"], L["description"] or "",
            f"{L['debit']:,.2f}", f"{L['credit']:,.2f}", f"{L['balance']:,.2f}",
        ])
    foot = [
        f"Reconciled: {sym}{data['totals']['reconciled']:,.2f}",
        f"Outstanding: {sym}{data['totals']['outstanding']:,.2f}",
        f"Book balance: {sym}{data['totals']['book_balance']:,.2f}",
    ]
    buf = build_pdf(co, "BANK RECONCILIATION STATEMENT", headers, rows, code, sym, True, foot)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": "attachment; filename=bank_reconciliation.pdf"})


@app.get("/api/reports/trial-balance/pdf")
def trial_balance_pdf(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    data = trial_balance(current_user, db)
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Code", "Name", "Type", "Project", f"Debit ({sym})", f"Credit ({sym})", "Balance"]
    rows = [[r["code"], r["name"], r["type"], r["project_code"], f"{r['debit']:,.2f}", f"{r['credit']:,.2f}", f"{r['balance']:,.2f}"] for r in data["rows"]]
    foot = [f"Total Debit: {sym}{data['total_debit']:,.2f}", f"Total Credit: {sym}{data['total_credit']:,.2f}",
            "BALANCED" if data["balanced"] else "OUT OF BALANCE"]
    buf = build_pdf(co, "TRIAL BALANCE", headers, rows, code, sym, True, foot)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": "attachment; filename=trial_balance.pdf"})


@app.get("/api/reports/ledger/pdf")
def ledger_pdf(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    data = general_ledger(current_user, db)
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Entry", "Date", "Source", "Account", "Description", f"Debit ({sym})", f"Credit ({sym})"]
    rows = [[r["entry_no"], r["date"], r["source_type"], r["account"], r["description"], f"{r['debit']:,.2f}", f"{r['credit']:,.2f}"] for r in data]
    buf = build_pdf(co, "GENERAL LEDGER", headers, rows, code, sym, True)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": "attachment; filename=general_ledger.pdf"})


@app.get("/api/reports/budget-variance/pdf")
def variance_pdf(project_code: Optional[str] = None, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    data = budget_variance(project_code, current_user, db)
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Budget Code", "Description", f"Budgeted ({sym})", f"Actual ({sym})", f"Variance ({sym})", "Remark"]
    rows = [[r["budget_code"], r["description"], f"{r['budgeted']:,.2f}", f"{r['actual']:,.2f}", f"{r['variance']:,.2f}", r["remark"]] for r in data["rows"]]
    rows.append(["", "TOTAL", f"{data['total_budget']:,.2f}", f"{data['total_actual']:,.2f}", f"{data['total_variance']:,.2f}", ""])
    buf = build_pdf(co, f"BUDGET VARIANCE — {data['project_code']}", headers, rows, code, sym, True)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": "attachment; filename=budget_variance.pdf"})


@app.get("/api/reports/assets/pdf")
def assets_pdf(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    assets = db.query(Asset).filter(Asset.company_id == current_user.company_id).all()
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Number", "Name", "Category", "Assigned", "Cost", "NBV", "Condition", "Status", "Insurance"]
    rows = [[a.asset_number, a.asset_name, a.category or "", a.assigned_to or "", f"{(a.cost or 0):,.2f}", f"{(a.nbv or 0):,.2f}", a.condition or "", a.status or "", a.insurance or ""] for a in assets]
    buf = build_pdf(co, "FIXED ASSET REGISTER", headers, rows, code, sym, True)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=assets.pdf"})


@app.get("/api/reports/inventory/pdf")
def inventory_pdf(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    items = db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id).all()
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Code", "Name", "Category", "Dept", "Cost", "Balance", "Value"]
    rows = [[i.item_code, i.item_name, i.category or "", i.department or "", f"{(i.cost_price or 0):,.2f}", i.balance_qty, f"{(i.total_value or 0):,.2f}"] for i in items]
    buf = build_pdf(co, "INVENTORY REGISTER", headers, rows, code, sym, True)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=inventory.pdf"})


@app.get("/api/reports/vendors/pdf")
def vendors_pdf(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    vendors = db.query(Vendor).filter(Vendor.company_id == current_user.company_id).all()
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["No", "Name", "Tax", "Score", "Amount", "Bank", "Description"]
    rows = [[v.vendor_number, v.name, v.tax_clearance or "", v.score, f"{(v.amount or 0):,.2f}", v.bank or "", (v.description or "")[:40]] for v in vendors]
    buf = build_pdf(co, "VENDOR / PROCUREMENT REGISTER", headers, rows, code, sym, True)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=vendors.pdf"})


@app.get("/api/reports/payments/pdf")
def payments_pdf(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    pays = db.query(PaymentRequest).filter(PaymentRequest.company_id == current_user.company_id).all()
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Request No", "Payee", "Amount", "Status", "Narration"]
    rows = [[p.request_no, p.payee_name or "", f"{p.amount:,.2f}", p.status, (p.narration or "")[:40]] for p in pays]
    buf = build_pdf(co, "PAYMENT REQUESTS", headers, rows, code, sym, True)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=payments.pdf"})


# Single payment voucher PDF
@app.get("/api/reports/voucher/{pid}/pdf")
def voucher_pdf(pid: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    try:
        from reports import company_header, table_style
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm, cm
        from reportlab.lib import colors
        from io import BytesIO

        pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
        if not pr:
            raise HTTPException(404, "Payment request not found")
        co, code, sym = _company_and_currency(db, current_user)
        exp = db.query(ExpenseCode).filter(ExpenseCode.id == pr.expense_code_id).first() if pr.expense_code_id else None
        bud = db.query(BudgetCode).filter(BudgetCode.id == pr.budget_code_id).first() if pr.budget_code_id else None
        debit = db.query(ChartOfAccount).filter(ChartOfAccount.id == pr.debit_account_id).first() if pr.debit_account_id else None
        credit = db.query(ChartOfAccount).filter(ChartOfAccount.id == pr.credit_account_id).first() if pr.credit_account_id else None
        proj = None
        try:
            if pr.project_code_id:
                proj = db.query(ProjectCode).filter(ProjectCode.id == pr.project_code_id).first()
        except Exception:
            pass
        requester = db.query(User).filter(User.id == pr.requester_id).first()
        prog_u = db.query(User).filter(User.id == pr.program_approved_by).first() if pr.program_approved_by else None
        fin_u = db.query(User).filter(User.id == pr.finance_approved_by).first() if pr.finance_approved_by else None
        lines = db.query(PaymentLine).filter(PaymentLine.payment_request_id == pr.id).order_by(PaymentLine.sort_order).all()

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm)
        story = []
        styles = company_header(story, co, "PAYMENT VOUCHER", code, sym)
        data = [
            ["Field", "Value"],
            ["Voucher No", pr.request_no or ""],
            ["Status", pr.status or ""],
            ["Date", pr.created_at.strftime("%Y-%m-%d") if pr.created_at else ""],
            ["Payee", pr.payee_name or ""],
            ["Amount (figures)", f"{sym}{float(pr.amount or 0):,.2f}"],
            ["Amount (words)", amount_to_words(pr.amount or 0)],
            ["Budget code", f"{getattr(bud,'code','') or ''} — {getattr(bud,'description','') or ''}"],
            ["Expense code", f"{getattr(exp,'code','') or ''} — {getattr(exp,'description','') or ''}"],
            ["Project code", f"{getattr(proj,'code','') or ''} — {getattr(proj,'name','') or ''}"],
            ["Account debited", f"{debit.code} - {debit.name}" if debit else "NOT SET"],
            ["Account credited", f"{credit.code} - {credit.name}" if credit else "NOT SET"],
            ["Narration", (pr.narration or "")[:500]],
            ["Requested by", (requester.full_name or requester.username) if requester else ""],
            ["Program approved by", (prog_u.full_name or prog_u.username) if prog_u else ""],
            ["Finance approved by", (fin_u.full_name or fin_u.username) if fin_u else ""],
        ]
        # wrap cells
        wrapped = []
        for row in data:
            wrapped.append([Paragraph(str(row[0]), styles["Cell"]), Paragraph(str(row[1]).replace("\n","<br/>"), styles["Cell"])])
        tbl = Table(wrapped, colWidths=[50*mm, 120*mm])
        tbl.setStyle(table_style())
        story.append(tbl)
        if lines:
            story.append(Spacer(1, 10))
            story.append(Paragraph("Line items", styles["ReportH"]))
            ld = [["Description", "Qty", "Unit cost", "Amount"]]
            for L in lines:
                ld.append([L.description or "", f"{L.quantity or 0}", f"{L.unit_cost or 0:,.2f}", f"{L.amount or 0:,.2f}"])
            lt = Table(ld, colWidths=[80*mm, 25*mm, 30*mm, 35*mm])
            lt.setStyle(table_style())
            story.append(lt)
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            "Posted under double-entry principles to the general ledger on final payment (status: paid).",
            styles["Small"],
        ))
        doc.build(story)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f"attachment; filename=voucher_{pr.request_no or pid}.pdf"})
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(500, f"Voucher PDF failed: {ex}")



@app.post("/api/users/me/signature")
async def upload_my_signature(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "Upload a PNG or JPG signature image")
    content = await file.read()
    if len(content) > 500 * 1024:
        raise HTTPException(400, "Signature image max 500KB")
    fname = f"sig_user_{current_user.id}{ext}"
    dest = UPLOADS_DIR / fname
    dest.write_bytes(content)
    current_user.signature_path = f"/static/uploads/{fname}"
    db.commit()
    audit(db, current_user.company_id, current_user, "SIGNATURE_UPLOAD", fname)
    return {"signature_path": current_user.signature_path}


@app.get("/api/users/me/signature")
def get_my_signature(current_user: User = Depends(get_current_active_user)):
    return {"signature_path": current_user.signature_path}




@app.get("/api/reports/ifrs/financial-position")
def ifrs_financial_position(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Statement of Financial Position (IAS 1) — balances by account type."""
    from reports import ifrs_for
    cid = current_user.company_id
    accounts = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == cid).all()
    rows = []
    totals = {"Asset": 0.0, "Liability": 0.0, "Equity": 0.0, "Cash": 0.0}
    for acc in accounts:
        lines = db.query(JournalEntry).filter(JournalEntry.company_id == cid, JournalEntry.account_id == acc.id).all()
        bal = sum((l.debit or 0) - (l.credit or 0) for l in lines)
        if abs(bal) < 0.0001:
            continue
        # for liabilities/equity/income typically credit-normal: present as positive credit balance
        at = acc.account_type or "Asset"
        display = bal
        if at in ("Liability", "Equity", "Income"):
            display = -bal  # credit balances shown positive
        if at in totals:
            totals[at] = totals.get(at, 0) + display
        elif at == "Cash":
            totals["Cash"] += display
            totals["Asset"] += display
        rows.append({
            "code": acc.code, "name": acc.name, "type": at,
            "amount": display, "ifrs": ifrs_for(acc.name, at),
            "project_code": acc.project_code or "",
        })
    return {
        "title": "Statement of Financial Position",
        "standard": "IAS 1 Presentation of Financial Statements",
        "rows": rows,
        "totals": totals,
        "assets_total": totals.get("Asset", 0) + totals.get("Cash", 0),
        "liabilities_equity_total": totals.get("Liability", 0) + totals.get("Equity", 0),
    }


@app.get("/api/reports/ifrs/financial-performance")
def ifrs_financial_performance(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Statement of Financial Performance / P&L (IAS 1 / IFRS 15)."""
    from reports import ifrs_for
    cid = current_user.company_id
    accounts = db.query(ChartOfAccount).filter(
        ChartOfAccount.company_id == cid,
        ChartOfAccount.account_type.in_(["Income", "Expense"]),
    ).all()
    rows = []
    income = expense = 0.0
    for acc in accounts:
        lines = db.query(JournalEntry).filter(JournalEntry.company_id == cid, JournalEntry.account_id == acc.id).all()
        bal = sum((l.debit or 0) - (l.credit or 0) for l in lines)
        if acc.account_type == "Income":
            amt = -bal  # credits increase income
            income += amt
        else:
            amt = bal
            expense += amt
        if abs(amt) < 0.0001:
            continue
        rows.append({
            "code": acc.code, "name": acc.name, "type": acc.account_type,
            "amount": amt, "ifrs": ifrs_for(acc.name, acc.account_type),
            "project_code": acc.project_code or "",
        })
    return {
        "title": "Statement of Financial Performance",
        "standard": "IAS 1; IFRS 15 Revenue from Contracts with Customers",
        "rows": rows,
        "total_income": income,
        "total_expense": expense,
        "surplus_deficit": income - expense,
    }


@app.get("/api/reports/ifrs/cash-flow")
def ifrs_cash_flow(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Statement of Cash Flows (IAS 7) — simplified classification by source_type."""
    from reports import ifrs_for
    cid = current_user.company_id
    cash_ids = [a.id for a in db.query(ChartOfAccount).filter(
        ChartOfAccount.company_id == cid, ChartOfAccount.account_type == "Cash"
    ).all()]
    lines = db.query(JournalEntry).filter(
        JournalEntry.company_id == cid,
        JournalEntry.account_id.in_(cash_ids) if cash_ids else False,
    ).order_by(JournalEntry.entry_date).all()
    buckets = {"Operating activities": 0.0, "Investing activities": 0.0, "Financing activities": 0.0}
    rows = []
    for j in lines:
        net = (j.debit or 0) - (j.credit or 0)
        src = (j.source_type or "manual").lower()
        if src in ("payment", "inventory", "manual", "vendor"):
            bucket = "Operating activities"
        elif src in ("asset", "asset_adjustment"):
            bucket = "Investing activities"
        else:
            bucket = "Operating activities"
        buckets[bucket] += net
        rows.append({
            "date": str(j.entry_date), "entry_no": j.entry_no,
            "description": j.description, "source_type": j.source_type,
            "amount": net, "classification": bucket,
            "ifrs": ifrs_for(bucket, "Cash"),
        })
    return {
        "title": "Statement of Cash Flows",
        "standard": "IAS 7 Statement of Cash Flows",
        "rows": rows,
        "totals": buckets,
        "net_change": sum(buckets.values()),
    }


@app.get("/api/reports/ifrs/{report_type}/pdf")
def ifrs_report_pdf(report_type: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    try:
        from ifrs_statements import build_sfp, build_pl, build_equity, build_cashflow
        co, code, sym = _company_and_currency(db, current_user)
        year = str(datetime.utcnow().year)
        prior = str(datetime.utcnow().year - 1)
        cid = current_user.company_id
        amounts = {}
        if cid:
            accounts = db.query(ChartOfAccount).filter(ChartOfAccount.company_id == cid).all()
            for acc in accounts:
                lines = db.query(JournalEntry).filter(JournalEntry.company_id == cid, JournalEntry.account_id == acc.id).all()
                bal = sum((l.debit or 0) - (l.credit or 0) for l in lines)
                at = (acc.account_type or "").lower()
                name = (acc.name or "").lower()
                if at == "cash" or "cash" in name or "bank" in name:
                    amounts["cash"] = amounts.get("cash", 0) + bal
                elif at == "asset":
                    if "receivable" in name:
                        amounts["receivables"] = amounts.get("receivables", 0) + bal
                    elif "inventor" in name:
                        amounts["inventory"] = amounts.get("inventory", 0) + bal
                    elif any(x in name for x in ("property", "plant", "equipment", "ppe", "fixed")):
                        amounts["ppe"] = amounts.get("ppe", 0) + bal
                    else:
                        amounts["other_ca"] = amounts.get("other_ca", 0) + bal
                elif at == "liability":
                    if "payable" in name:
                        amounts["payables"] = amounts.get("payables", 0) + (-bal)
                    else:
                        amounts["other_cl"] = amounts.get("other_cl", 0) + (-bal)
                elif at == "equity":
                    amounts["retained"] = amounts.get("retained", 0) + (-bal)
                elif at == "income":
                    amounts["revenue"] = amounts.get("revenue", 0) + (-bal)
                elif at == "expense":
                    amounts["admin"] = amounts.get("admin", 0) + bal
        amounts["total_ca"] = sum(amounts.get(k, 0) for k in ("cash", "receivables", "inventory", "other_ca", "cta"))
        amounts["total_nca"] = sum(amounts.get(k, 0) for k in ("ppe", "inv_prop", "intangible", "associates", "fin_assets", "dta", "other_nca"))
        amounts["total_assets"] = amounts.get("total_ca", 0) + amounts.get("total_nca", 0)
        amounts["total_cl"] = sum(amounts.get(k, 0) for k in ("payables", "c_borrowings", "ctl", "c_provisions", "other_cl"))
        amounts["total_ncl"] = sum(amounts.get(k, 0) for k in ("nc_borrowings", "dtl", "nc_provisions", "other_ncl"))
        amounts["total_liab"] = amounts.get("total_cl", 0) + amounts.get("total_ncl", 0)
        amounts["total_equity"] = amounts.get("retained", 0) + amounts.get("share_capital", 0) + amounts.get("share_premium", 0) + amounts.get("other_reserves", 0)
        amounts["total_equity_owners"] = amounts["total_equity"]
        amounts["total_equity_liab"] = amounts["total_equity"] + amounts["total_liab"]
        amounts["gross_profit"] = amounts.get("revenue", 0) - amounts.get("cos", 0)
        amounts["operating_profit"] = amounts["gross_profit"] + amounts.get("other_income", 0) - amounts.get("admin", 0) - amounts.get("distribution", 0) - amounts.get("other_exp", 0)
        amounts["pbt"] = amounts["operating_profit"] + amounts.get("fin_income", 0) - amounts.get("fin_costs", 0)
        amounts["profit_year"] = amounts["pbt"] - amounts.get("tax", 0)
        amounts["profit_cont"] = amounts["profit_year"]
        amounts["tci"] = amounts["profit_year"]
        amounts["cash_close"] = amounts.get("cash", 0)
        amounts["net_ops"] = amounts.get("pbt", 0)
        rt = (report_type or "").lower().replace("_", "-")
        if rt in ("financial-position", "position", "sfp"):
            buf = build_sfp(co, year, prior, amounts)
            fname = "statement_of_financial_position.pdf"
        elif rt in ("financial-performance", "performance", "pl"):
            buf = build_pl(co, year, prior, amounts)
            fname = "statement_of_profit_or_loss.pdf"
        elif rt in ("equity", "changes-in-equity"):
            buf = build_equity(co, year, amounts)
            fname = "statement_of_changes_in_equity.pdf"
        elif rt in ("cash-flow", "cashflow"):
            buf = build_cashflow(co, year, prior, amounts)
            fname = "statement_of_cash_flows.pdf"
        else:
            raise HTTPException(404, f"Unknown IFRS report type: {report_type}")
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f"attachment; filename={fname}"})
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(500, f"IFRS PDF failed: {ex}")



@app.get("/api/procurement/rfqs")
def list_rfqs(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not (current_user.can_access_vendors or current_user.role in ("company_admin", "finance", "superadmin", "project_manager")):
        raise HTTPException(403, "No procurement access")
    rows = db.query(RFQ).filter(RFQ.company_id == current_user.company_id).order_by(RFQ.id.desc()).all()
    return rows


@app.post("/api/procurement/rfqs")
def create_rfq(
    title: str = Form(...),
    description: str = Form(""),
    deadline: str = Form(...),
    items_json: str = Form("[]"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not current_user.company_id:
        raise HTTPException(403, "Company users only")
    if not (getattr(current_user, "can_access_vendors", False) or current_user.role in ("company_admin", "superadmin", "finance", "project_manager")):
        raise HTTPException(403, "Procurement access required")
    try:
        dl = datetime.fromisoformat(deadline.replace("Z", "+00:00").replace("+00:00", ""))
    except Exception:
        try:
            dl = datetime.strptime(deadline[:16], "%Y-%m-%dT%H:%M")
        except Exception:
            try:
                dl = datetime.strptime(deadline[:10], "%Y-%m-%d").replace(hour=23, minute=59)
            except Exception:
                raise HTTPException(400, "Invalid deadline format")
    try:
        rfq = RFQ(
            company_id=current_user.company_id,
            rfq_no=_rfq_no(db, current_user.company_id),
            title=title.strip(), description=description or "", deadline=dl,
            status="open", created_by=current_user.id,
        )
        db.add(rfq)
        db.commit()
        db.refresh(rfq)
        import json as _json
        try:
            items = _json.loads(items_json or "[]")
        except Exception:
            items = []
        for i, it in enumerate(items):
            db.add(RFQLineItem(
                rfq_id=rfq.id,
                description=str(it.get("description") or "Item"),
                quantity=float(it.get("quantity") or 1),
                unit=str(it.get("unit") or "unit"),
                conditions=str(it.get("conditions") or ""),
                sort_order=i,
            ))
        db.commit()
        audit(db, current_user.company_id, current_user, "RFQ_CREATE", rfq.rfq_no)
        return {
            "id": rfq.id, "rfq_no": rfq.rfq_no, "title": rfq.title,
            "description": rfq.description, "deadline": rfq.deadline.isoformat() if rfq.deadline else None,
            "status": rfq.status,
        }
    except HTTPException:
        raise
    except Exception as ex:
        db.rollback()
        raise HTTPException(500, f"Could not create RFQ: {ex}")


@app.get("/api/procurement/rfqs/{rfq_id}")
def get_rfq(rfq_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id, RFQ.company_id == current_user.company_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    links = db.query(RFQQuoteLink).filter(RFQQuoteLink.rfq_id == rfq.id).all()
    quotes = db.query(RFQQuote).filter(RFQQuote.rfq_id == rfq.id).all()
    members = db.query(RFQCommitteeMember).filter(RFQCommitteeMember.rfq_id == rfq.id).all()
    scores = db.query(RFQQuoteScore).filter(RFQQuoteScore.rfq_id == rfq.id).all()
    pos = db.query(PurchaseOrder).filter(PurchaseOrder.rfq_id == rfq.id).all()
    base = _public_base()
    return {
        "rfq": rfq,
        "links": [{
            "id": L.id, "token": L.token, "vendor_name": L.vendor_name, "vendor_email": L.vendor_email,
            "status": L.status, "expires_at": L.expires_at.isoformat() if L.expires_at else None,
            "url": f"{base}/quote/{L.token}" if base else f"/quote/{L.token}",
        } for L in links],
        "quotes": quotes,
        "committee": [{
            "id": m.id, "user_id": m.user_id, "role_label": m.role_label,
            "name": (db.query(User).filter(User.id == m.user_id).first() or User()).full_name
                or (db.query(User).filter(User.id == m.user_id).first() or User()).username,
        } for m in members],
        "scores": scores,
        "purchase_orders": pos,
    }


@app.post("/api/procurement/rfqs/{rfq_id}/invite")
def create_quote_link(
    rfq_id: int,
    vendor_name: str = Form(...),
    vendor_email: str = Form(""),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id, RFQ.company_id == current_user.company_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    if rfq.status not in ("open",):
        raise HTTPException(400, "RFQ is not open for invites")
    if rfq.deadline < datetime.utcnow():
        rfq.status = "closed"
        db.commit()
        raise HTTPException(400, "RFQ deadline has passed")
    token = secrets.token_urlsafe(24)
    link = RFQQuoteLink(
        company_id=current_user.company_id, rfq_id=rfq.id, token=token,
        vendor_name=vendor_name, vendor_email=vendor_email,
        status="pending", expires_at=rfq.deadline,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    base = _public_base()
    url = f"{base}/quote/{token}" if base else f"/quote/{token}"
    audit(db, current_user.company_id, current_user, "RFQ_INVITE", f"{rfq.rfq_no} → {vendor_name}")
    return {"id": link.id, "token": token, "url": url, "expires_at": link.expires_at.isoformat(), "vendor_name": vendor_name}


# ---- Public quote form (no auth) ----
@app.get("/api/public/quote/{token}")
def public_quote_get(token: str, db: Session = Depends(get_db)):
    link = db.query(RFQQuoteLink).filter(RFQQuoteLink.token == token).first()
    if not link:
        raise HTTPException(404, "Invalid link")
    rfq = db.query(RFQ).filter(RFQ.id == link.rfq_id).first()
    co = db.query(Company).filter(Company.id == link.company_id).first()
    items = db.query(RFQLineItem).filter(RFQLineItem.rfq_id == link.rfq_id).order_by(RFQLineItem.sort_order).all()
    existing = db.query(RFQQuote).filter(RFQQuote.link_id == link.id).first()
    expired = bool(link.expires_at and link.expires_at < datetime.utcnow())
    received = link.status == "received"
    valid = link.status == "pending" and not expired and not existing
    msg = ""
    if received:
        msg = "Your submission has been received by the procurement officer. This link is closed."
    elif existing:
        msg = "You have already submitted a quotation. Awaiting procurement acknowledgement."
    elif expired or link.status == "expired":
        msg = "This quotation link has expired."
    return {
        "valid": valid,
        "received": received,
        "already_submitted": bool(existing),
        "message": msg,
        "rfq_no": rfq.rfq_no if rfq else "",
        "title": rfq.title if rfq else "",
        "description": rfq.description if rfq else "",
        "deadline": rfq.deadline.isoformat() if rfq and rfq.deadline else None,
        "conditions": rfq.description if rfq else "",
        "vendor_name": link.vendor_name,
        "vendor_email": link.vendor_email,
        "company_label": (co.name if co else "Organisation"),  # minimal label only
        "items": [{"id": it.id, "description": it.description, "quantity": it.quantity, "unit": it.unit, "conditions": it.conditions} for it in items],
    }


@app.post("/api/public/quote/{token}")
async def public_quote_submit(
    token: str,
    vendor_name: str = Form(...),
    vendor_email: str = Form(""),
    vendor_phone: str = Form(""),
    amount: float = Form(0),
    notes: str = Form(""),
    cac_number: str = Form(""),
    tax_clearance: str = Form(""),
    qualification: str = Form(""),
    bank_name: str = Form(""),
    bank_account: str = Form(""),
    bank_account_name: str = Form(""),
    consent_capable: str = Form("false"),
    validity_days: int = Form(30),
    lines_json: str = Form("[]"),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    link = db.query(RFQQuoteLink).filter(RFQQuoteLink.token == token).first()
    if not link:
        raise HTTPException(404, "Invalid link")
    if link.status != "pending" or (link.expires_at and link.expires_at < datetime.utcnow()):
        raise HTTPException(400, "This link is no longer accepting submissions")
    if db.query(RFQQuote).filter(RFQQuote.link_id == link.id).first():
        raise HTTPException(400, "Quote already submitted")
    if consent_capable.lower() not in ("true", "1", "yes", "on"):
        raise HTTPException(400, "You must consent that you are ready and able to provide the goods/services")
    att = None
    if file and file.filename:
        content = await file.read()
        # practical limit 25MB (browser uploads; 500MB is not viable for typical hosting)
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(400, "Attachment max 25MB")
        ext = Path(file.filename).suffix.lower()
        if ext not in (".pdf", ".png", ".jpg", ".jpeg"):
            raise HTTPException(400, "Upload PDF or image of letter-head quotation")
        fname = f"quote_{link.id}_{secrets.token_hex(4)}{ext}"
        (UPLOADS_DIR / fname).write_bytes(content)
        att = f"/static/uploads/{fname}"
    quote = RFQQuote(
        company_id=link.company_id, rfq_id=link.rfq_id, link_id=link.id,
        vendor_name=vendor_name or link.vendor_name,
        vendor_email=vendor_email or link.vendor_email,
        vendor_phone=vendor_phone, amount=amount, notes=notes,
        validity_days=validity_days, attachment_path=att, status="submitted",
        cac_number=cac_number, tax_clearance=tax_clearance, qualification=qualification,
        bank_name=bank_name, bank_account=bank_account, bank_account_name=bank_account_name,
        consent_capable=True,
    )
    link.status = "submitted"
    existing = db.query(Vendor).filter(Vendor.company_id == link.company_id, Vendor.name == quote.vendor_name).first()
    if not existing:
        db.add(Vendor(
            company_id=link.company_id, vendor_number=f"V-RFQ-{link.id}", name=quote.vendor_name,
            description=f"CAC:{cac_number} Tax:{tax_clearance}", amount=amount,
            cac_number=cac_number or "", tax_clearance=tax_clearance or "",
            bank=bank_name or "",
        ))
    db.add(quote)
    db.commit()
    db.refresh(quote)
    import json as _json
    try:
        qlines = _json.loads(lines_json or "[]")
    except Exception:
        qlines = []
    total_lines = 0.0
    for L in qlines:
        qty = float(L.get("quantity") or 1)
        uc = float(L.get("unit_cost") or 0)
        amt = float(L.get("amount") or qty * uc)
        total_lines += amt
        try:
            db.add(RFQQuoteLine(
                quote_id=quote.id, description=L.get("description") or "",
                quantity=qty, unit=L.get("unit") or "unit", unit_cost=uc, amount=amt,
            ))
        except Exception:
            pass
    if total_lines > 0:
        quote.amount = total_lines
    db.commit()
    return {"message": "Quotation submitted. Await procurement acknowledgement that your submission was received.", "quote_id": quote.id}


@app.post("/api/procurement/quotes/{quote_id}/receive")
def mark_quote_received(quote_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    q = db.query(RFQQuote).filter(RFQQuote.id == quote_id, RFQQuote.company_id == current_user.company_id).first()
    if not q:
        raise HTTPException(404, "Quote not found")
    q.status = "received"
    q.received_at = datetime.utcnow()
    if q.link_id:
        link = db.query(RFQQuoteLink).filter(RFQQuoteLink.id == q.link_id).first()
        if link:
            link.status = "received"
            link.received_at = datetime.utcnow()
            link.received_by = current_user.id
            # expire link
            link.expires_at = datetime.utcnow()
    db.commit()
    audit(db, current_user.company_id, current_user, "QUOTE_RECEIVED", f"quote {quote_id}")
    return {"message": "Marked received. Vendor link now shows acknowledgement and is closed."}


@app.post("/api/procurement/rfqs/{rfq_id}/committee")
def add_committee_member(
    rfq_id: int,
    user_id: int = Form(...),
    role_label: str = Form("Member"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id, RFQ.company_id == current_user.company_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    u = db.query(User).filter(User.id == user_id, User.company_id == current_user.company_id).first()
    if not u:
        raise HTTPException(400, "User not in company")
    m = RFQCommitteeMember(company_id=current_user.company_id, rfq_id=rfq_id, user_id=user_id, role_label=role_label)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@app.post("/api/procurement/quotes/{quote_id}/score")
def score_quote(
    quote_id: int,
    score: float = Form(...),
    comments: str = Form(""),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if score < 0 or score > 100:
        raise HTTPException(400, "Score must be 0–100")
    q = db.query(RFQQuote).filter(RFQQuote.id == quote_id, RFQQuote.company_id == current_user.company_id).first()
    if not q:
        raise HTTPException(404, "Quote not found")
    # must be committee member or admin
    is_member = db.query(RFQCommitteeMember).filter(
        RFQCommitteeMember.rfq_id == q.rfq_id, RFQCommitteeMember.user_id == current_user.id
    ).first()
    if not is_member and current_user.role not in ("company_admin", "superadmin"):
        raise HTTPException(403, "Only committee members can score")
    existing = db.query(RFQQuoteScore).filter(
        RFQQuoteScore.quote_id == quote_id, RFQQuoteScore.member_id == current_user.id
    ).first()
    if existing:
        existing.score = score
        existing.comments = comments
    else:
        db.add(RFQQuoteScore(
            company_id=current_user.company_id, rfq_id=q.rfq_id, quote_id=quote_id,
            member_id=current_user.id, score=score, comments=comments,
        ))
    db.commit()
    # recompute average
    all_s = db.query(RFQQuoteScore).filter(RFQQuoteScore.quote_id == quote_id).all()
    q.total_score = sum(s.score for s in all_s) / max(len(all_s), 1)
    q.status = "scored"
    db.commit()
    return {"message": "Score saved", "total_score": q.total_score}


@app.post("/api/procurement/rfqs/{rfq_id}/declare-winner")
def declare_winner(rfq_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id, RFQ.company_id == current_user.company_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    quotes = db.query(RFQQuote).filter(RFQQuote.rfq_id == rfq_id).all()
    if not quotes:
        raise HTTPException(400, "No quotes to evaluate")
    winner = max(quotes, key=lambda q: (q.total_score or 0, -(q.amount or 0)))
    for q in quotes:
        q.status = "winner" if q.id == winner.id else "rejected"
    rfq.winner_quote_id = winner.id
    rfq.status = "awarded"
    token = secrets.token_urlsafe(24)
    po = PurchaseOrder(
        company_id=current_user.company_id,
        po_no=_po_no(db, current_user.company_id),
        rfq_id=rfq.id, quote_id=winner.id,
        vendor_name=winner.vendor_name, vendor_email=winner.vendor_email or "",
        amount=winner.amount, description=f"PO from {rfq.rfq_no}: {rfq.title}",
        status="pending_vendor", result_token=token, created_by=current_user.id,
    )
    db.add(po)
    # result links for all vendors (share on each line)
    for q in quotes:
        if q.id == winner.id:
            continue
        # losers can still get a token via quote-level result - store on a simple field via new PO only for winner
        pass
    db.commit()
    db.refresh(po)
    audit(db, current_user.company_id, current_user, "RFQ_WINNER", f"{rfq.rfq_no} → {winner.vendor_name}")
    base = _public_base()
    return {
        "winner": winner,
        "purchase_order": po,
        "result_url": f"{base}/po-result/{token}" if base else f"/po-result/{token}",
        "message": f"Winner: {winner.vendor_name} (score {winner.total_score})",
    }


@app.get("/api/procurement/rfqs/{rfq_id}/committee-report/pdf")
def committee_report_pdf(rfq_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from reports import company_header, table_style
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from io import BytesIO
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id, RFQ.company_id == current_user.company_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    co, code, sym = _company_and_currency(db, current_user)
    quotes = db.query(RFQQuote).filter(RFQQuote.rfq_id == rfq_id).order_by(RFQQuote.total_score.desc()).all()
    members = db.query(RFQCommitteeMember).filter(RFQCommitteeMember.rfq_id == rfq_id).all()
    scores = db.query(RFQQuoteScore).filter(RFQQuoteScore.rfq_id == rfq_id).all()
    winner = next((q for q in quotes if q.status == "winner"), None)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm)
    story = []
    styles = company_header(story, co, "PROCUREMENT COMMITTEE EVALUATION REPORT", code, sym)
    story.append(Paragraph(f"<b>1. INTRODUCTION</b>", styles["ReportH"]))
    story.append(Paragraph(
        f"This report presents the evaluation of quotations received under RFQ <b>{rfq.rfq_no}</b> — {rfq.title}. "
        f"A total of <b>{len(quotes)}</b> vendor(s) submitted bids. The procurement committee assessed each submission "
        f"and awarded scores. The vendor with the highest average score is recommended for award.",
        styles["Cell"],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>2. COMMITTEE MEMBERS</b>", styles["ReportH"]))
    for m in members:
        u = db.query(User).filter(User.id == m.user_id).first()
        story.append(Paragraph(f"• {(u.full_name or u.username) if u else m.user_id} — {m.role_label}", styles["Cell"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>3. BID EVALUATION SUMMARY</b>", styles["ReportH"]))
    data = [["Vendor", "Amount", "Avg Score", "Status", "Email"]]
    for q in quotes:
        data.append([q.vendor_name, f"{sym}{q.amount:,.2f}", f"{(q.total_score or 0):.1f}", q.status, q.vendor_email or ""])
    t = Table(data, colWidths=[45*mm, 30*mm, 25*mm, 25*mm, 45*mm])
    t.setStyle(table_style())
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>4. DETAILED SCORES & COMMENTS</b>", styles["ReportH"]))
    for q in quotes:
        story.append(Paragraph(f"<b>{q.vendor_name}</b> (Amount {sym}{q.amount:,.2f})", styles["Cell"]))
        for s in scores:
            if s.quote_id == q.id:
                mu = db.query(User).filter(User.id == s.member_id).first()
                nm = (mu.full_name or mu.username) if mu else str(s.member_id)
                story.append(Paragraph(f"&nbsp;&nbsp;{nm}: score {s.score} — {s.comments or 'No comment'}", styles["Small"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>5. RECOMMENDATION</b>", styles["ReportH"]))
    if winner:
        story.append(Paragraph(
            f"The committee recommends <b>{winner.vendor_name}</b> with average score <b>{(winner.total_score or 0):.1f}</b> "
            f"and quoted amount <b>{sym}{winner.amount:,.2f}</b> for award of the purchase order.",
            styles["Cell"],
        ))
    else:
        story.append(Paragraph("Winner not yet declared.", styles["Cell"]))
    story.append(Spacer(1, 16))
    story.append(Paragraph("___________________________ &nbsp;&nbsp; ___________________________", styles["Small"]))
    story.append(Paragraph("Committee Chair &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Procurement Officer", styles["Small"]))
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename=committee_{rfq.rfq_no}.pdf"})



@app.get("/api/procurement/pos/{po_id}/pdf")
def purchase_order_pdf(po_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from reports import company_header, table_style
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from io import BytesIO
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po:
        raise HTTPException(404, "PO not found")
    co, code, sym = _company_and_currency(db, current_user)
    quote = db.query(RFQQuote).filter(RFQQuote.id == po.quote_id).first() if po.quote_id else None
    qlines = []
    if quote:
        try:
            qlines = db.query(RFQQuoteLine).filter(RFQQuoteLine.quote_id == quote.id).all()
        except Exception:
            qlines = []
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm)
    story = []
    styles = company_header(story, co, "PURCHASE ORDER", code, sym)
    story.append(Paragraph(f"<b>PO No:</b> {po.po_no} &nbsp;&nbsp; <b>Date:</b> {po.created_at.strftime('%Y-%m-%d') if po.created_at else ''}", styles["Cell"]))
    story.append(Paragraph(f"<b>Vendor:</b> {po.vendor_name}", styles["Cell"]))
    story.append(Paragraph(f"<b>Status:</b> {po.status}", styles["Cell"]))
    story.append(Spacer(1, 8))
    if qlines:
        data = [["Description", "Qty", "Unit", "Unit cost", "Amount"]]
        for L in qlines:
            data.append([L.description or "", f"{L.quantity or 0}", L.unit or "", f"{L.unit_cost or 0:,.2f}", f"{L.amount or 0:,.2f}"])
        data.append(["", "", "", "TOTAL", f"{po.amount or 0:,.2f}"])
    else:
        data = [["Description", "Amount"], [po.description or "Supply as per RFQ quotation", f"{sym}{po.amount or 0:,.2f}"]]
    t = Table(data, colWidths=[70*mm, 25*mm, 25*mm, 30*mm, 30*mm][:len(data[0])])
    t.setStyle(table_style())
    story.append(t)
    story.append(Spacer(1, 16))
    story.append(Paragraph("Authorised for and on behalf of the organisation.", styles["Small"]))
    story.append(Paragraph("_________________________ &nbsp;&nbsp;&nbsp; _________________________", styles["Small"]))
    story.append(Paragraph("Procurement &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Approving officer", styles["Small"]))
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={po.po_no}.pdf"})


@app.get("/api/procurement/pos")
def list_pos(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return db.query(PurchaseOrder).filter(PurchaseOrder.company_id == current_user.company_id).order_by(PurchaseOrder.id.desc()).all()


@app.get("/api/procurement/pos/{po_id}/result-link")
def po_result_link(po_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po:
        raise HTTPException(404, "PO not found")
    if not po.result_token:
        po.result_token = secrets.token_urlsafe(24)
        db.commit()
    base = _public_base()
    return {"url": f"{base}/po-result/{po.result_token}" if base else f"/po-result/{po.result_token}", "token": po.result_token}


@app.get("/api/public/po-result/{token}")
def public_po_result(token: str, db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.result_token == token).first()
    if not po:
        raise HTTPException(404, "Invalid link")
    return {
        "po_no": po.po_no,
        "vendor_name": po.vendor_name,
        "amount": po.amount,
        "description": po.description,
        "status": po.status,
        "vendor_response": po.vendor_response,
        "successful": po.status in ("pending_vendor", "accepted", "sent_to_finance", "paid") and True,
        "can_respond": po.status == "pending_vendor" and not po.vendor_response,
    }


@app.post("/api/public/po-result/{token}")
def public_po_respond(token: str, response: str = Form(...), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.result_token == token).first()
    if not po:
        raise HTTPException(404, "Invalid link")
    if po.status != "pending_vendor":
        raise HTTPException(400, "This offer can no longer be accepted or rejected")
    response = response.lower().strip()
    if response not in ("accepted", "rejected"):
        raise HTTPException(400, "response must be accepted or rejected")
    po.vendor_response = response
    po.vendor_response_at = datetime.utcnow()
    po.status = "accepted" if response == "accepted" else "rejected"
    db.commit()
    return {"message": f"You have {response} the purchase order {po.po_no}", "status": po.status}


@app.post("/api/procurement/pos/{po_id}/send-to-finance")
def po_to_finance(
    po_id: int,
    debit_account_id: int = Form(...),
    credit_account_id: int = Form(...),
    project_code_id: Optional[int] = Form(None),
    budget_code_id: Optional[int] = Form(None),
    expense_code_id: Optional[int] = Form(None),
    designated_approver_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po:
        raise HTTPException(404, "PO not found")
    if po.status != "accepted":
        raise HTTPException(400, "Vendor must accept the PO before sending to finance")
    # need budget/expense - use first available if not provided
    if not budget_code_id:
        b = db.query(BudgetCode).filter(BudgetCode.company_id == current_user.company_id, BudgetCode.is_active == True).first()
        budget_code_id = b.id if b else None
    if not expense_code_id:
        e = db.query(ExpenseCode).filter(ExpenseCode.company_id == current_user.company_id, ExpenseCode.is_active == True).first()
        expense_code_id = e.id if e else None
    if not budget_code_id or not expense_code_id:
        raise HTTPException(400, "Company must have at least one budget code and expense code")
    if not designated_approver_id:
        designated_approver_id = current_user.id
    pr = PaymentRequest(
        company_id=current_user.company_id,
        request_no=next_request_no(db, current_user.company_id),
        requester_id=current_user.id,
        budget_code_id=budget_code_id,
        expense_code_id=expense_code_id,
        amount=po.amount,
        narration=f"PO {po.po_no}: {po.description}",
        payee_name=po.vendor_name,
        project_code_id=project_code_id,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        designated_approver_id=designated_approver_id,
        status="submitted",
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    po.payment_request_id = pr.id
    po.debit_account_id = debit_account_id
    po.credit_account_id = credit_account_id
    po.project_code_id = project_code_id
    po.status = "sent_to_finance"
    db.add(PaymentApprovalLog(
        payment_request_id=pr.id, actor_id=current_user.id, action="submit",
        comment=f"From PO {po.po_no}", amount_snapshot=pr.amount,
        debit_account_id=debit_account_id, credit_account_id=credit_account_id,
    ))
    db.commit()
    audit(db, current_user.company_id, current_user, "PO_TO_FINANCE", f"{po.po_no} → {pr.request_no}")
    return {"message": "Purchase order sent to finance as payment request", "payment_request_id": pr.id, "request_no": pr.request_no}


@app.get("/api/reports/po/{po_id}/pdf")
def po_pdf(po_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po:
        raise HTTPException(404, "Not found")
    co, code, sym = _company_and_currency(db, current_user)
    headers = ["Field", "Value"]
    rows = [
        ["PO No", po.po_no], ["Vendor", po.vendor_name], ["Amount", f"{sym}{po.amount:,.2f}"],
        ["Amount in words", amount_to_words(po.amount)], ["Description", po.description or ""],
        ["Status", po.status], ["Vendor response", po.vendor_response or "Pending"],
    ]
    buf = build_pdf(co, "PURCHASE ORDER", headers, rows, code, sym, False)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={po.po_no}.pdf"})




@app.post("/api/procurement/rfqs/{rfq_id}/committee-invite")
def committee_invite(
    rfq_id: int,
    user_id: Optional[int] = Form(None),
    invite_name: str = Form(""),
    invite_email: str = Form(""),
    password: str = Form(""),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Invite existing staff by user_id, or register a new committee user and return scoring link."""
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id, RFQ.company_id == current_user.company_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    uid = user_id
    if not uid and invite_email:
        # create user with limited access
        uname = (invite_email.split("@")[0] + "_cm")[:40]
        existing = db.query(User).filter(User.company_id == current_user.company_id, User.username == uname).first()
        if existing:
            uid = existing.id
        else:
            u = User(
                company_id=current_user.company_id, username=uname, email=invite_email,
                full_name=invite_name or uname,
                hashed_password=get_password_hash(password or secrets.token_urlsafe(8)),
                role="user", is_active=True, can_access_reports=True, can_access_vendors=True,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            uid = u.id
    if not uid:
        raise HTTPException(400, "Provide user_id or invite_email")
    if not db.query(RFQCommitteeMember).filter(RFQCommitteeMember.rfq_id == rfq_id, RFQCommitteeMember.user_id == uid).first():
        db.add(RFQCommitteeMember(company_id=current_user.company_id, rfq_id=rfq_id, user_id=uid, role_label="Committee"))
    tok = secrets.token_urlsafe(24)
    inv = RFQCommitteeInvite(
        company_id=current_user.company_id, rfq_id=rfq_id, user_id=uid,
        invite_email=invite_email, invite_name=invite_name, token=tok,
    )
    db.add(inv)
    db.commit()
    base = _public_base() if "_public_base" in dir() else ""
    try:
        base = _public_base()
    except Exception:
        base = ""
    url = f"{base}/committee-score/{tok}" if base else f"/committee-score/{tok}"
    return {"token": tok, "url": url, "user_id": uid, "message": "Share this scoring link with the committee member"}


def _try_auto_award(db, rfq_id, company_id):
    members = db.query(RFQCommitteeMember).filter(RFQCommitteeMember.rfq_id == rfq_id).all()
    if not members:
        return None
    quotes = db.query(RFQQuote).filter(RFQQuote.rfq_id == rfq_id, RFQQuote.status.in_(["submitted", "received", "scored"])).all()
    if not quotes:
        return None
    for q in quotes:
        scores = db.query(RFQQuoteScore).filter(RFQQuoteScore.quote_id == q.id).all()
        if len(scores) < len(members):
            return None  # not all members scored every quote
    # all scored — declare winner
    for q in quotes:
        sc = db.query(RFQQuoteScore).filter(RFQQuoteScore.quote_id == q.id).all()
        q.total_score = sum(s.score for s in sc) / len(sc) if sc else 0
        q.status = "scored"
    winner = max(quotes, key=lambda x: (x.total_score or 0, -(x.amount or 0)))
    for q in quotes:
        q.status = "winner" if q.id == winner.id else "rejected"
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    rfq.status = "awarded"
    rfq.winner_quote_id = winner.id
    token = secrets.token_urlsafe(24)
    po = PurchaseOrder(
        company_id=company_id, po_no=f"PO-{datetime.utcnow().strftime('%Y%m')}-{db.query(PurchaseOrder).filter(PurchaseOrder.company_id==company_id).count()+1:04d}",
        rfq_id=rfq_id, quote_id=winner.id, vendor_name=winner.vendor_name,
        amount=winner.amount, currency=winner.currency or "NGN",
        description=f"PO from {rfq.rfq_no}: {rfq.title}",
        status="pending_vendor", result_token=token,
    )
    db.add(po)
    db.commit()
    db.refresh(po)
    return po


@app.get("/api/public/committee-score/{token}")
def public_committee_get(token: str, db: Session = Depends(get_db)):
    inv = db.query(RFQCommitteeInvite).filter(RFQCommitteeInvite.token == token).first()
    if not inv:
        raise HTTPException(404, "Invalid committee link")
    rfq = db.query(RFQ).filter(RFQ.id == inv.rfq_id).first()
    quotes = db.query(RFQQuote).filter(RFQQuote.rfq_id == inv.rfq_id).all()
    out_q = []
    for q in quotes:
        my = db.query(RFQQuoteScore).filter(RFQQuoteScore.quote_id == q.id, RFQQuoteScore.member_id == inv.user_id).first()
        out_q.append({
            "id": q.id, "vendor_name": q.vendor_name, "amount": q.amount,
            "notes": q.notes, "attachment_path": q.attachment_path,
            "cac_number": getattr(q, "cac_number", ""), "tax_clearance": getattr(q, "tax_clearance", ""),
            "qualification": getattr(q, "qualification", ""),
            "my_score": my.score if my else None, "my_comments": my.comments if my else "",
            "locked": my is not None,
        })
    return {
        "rfq_no": rfq.rfq_no if rfq else "", "title": rfq.title if rfq else "",
        "submitted_all": inv.submitted, "quotes": out_q, "member_name": inv.invite_name,
    }


@app.post("/api/public/committee-score/{token}")
def public_committee_score(
    token: str,
    quote_id: int = Form(...),
    score: float = Form(...),
    comments: str = Form(""),
    db: Session = Depends(get_db),
):
    inv = db.query(RFQCommitteeInvite).filter(RFQCommitteeInvite.token == token).first()
    if not inv:
        raise HTTPException(404, "Invalid link")
    if score < 0 or score > 100:
        raise HTTPException(400, "Score 0-100")
    existing = db.query(RFQQuoteScore).filter(
        RFQQuoteScore.quote_id == quote_id, RFQQuoteScore.member_id == inv.user_id
    ).first()
    if existing:
        raise HTTPException(400, "Score already submitted and cannot be edited")
    db.add(RFQQuoteScore(
        company_id=inv.company_id, rfq_id=inv.rfq_id, quote_id=quote_id,
        member_id=inv.user_id, score=score, comments=comments,
    ))
    db.commit()
    # mark invite submitted if all quotes scored
    quotes = db.query(RFQQuote).filter(RFQQuote.rfq_id == inv.rfq_id).all()
    done = True
    for q in quotes:
        if not db.query(RFQQuoteScore).filter(RFQQuoteScore.quote_id == q.id, RFQQuoteScore.member_id == inv.user_id).first():
            done = False
            break
    if done:
        inv.submitted = True
        db.commit()
        po = _try_auto_award(db, inv.rfq_id, inv.company_id)
        if po:
            return {"message": "Scores complete. Winner auto-declared and PO created.", "auto_awarded": True, "po_no": po.po_no}
    return {"message": "Score submitted (locked)", "auto_awarded": False}




@app.get("/api/reports/bank-recon/pdf")
def bank_recon_pdf_std(
    account_id: int = None,
    statement_balance: float = 0,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from ifrs_statements import build_bank_recon
    co, code, sym = _company_and_currency(db, current_user)
    # book balance from ledger for cash account
    book = 0.0
    name = "Cash account"
    if account_id:
        acc = db.query(ChartOfAccount).filter(ChartOfAccount.id == account_id, ChartOfAccount.company_id == current_user.company_id).first()
        if acc:
            name = f"{acc.code} — {acc.name}"
            lines = db.query(JournalEntry).filter(JournalEntry.company_id == current_user.company_id, JournalEntry.account_id == account_id).all()
            book = sum((l.debit or 0) - (l.credit or 0) for l in lines)
    # outstanding from unticked recon items if any
    outstanding = deposits = 0.0
    try:
        # optional: sum unticked credits/debits if BankReconState exists
        pass
    except Exception:
        pass
    period = datetime.utcnow().strftime("%B %Y")
    buf = build_bank_recon(co, name, statement_balance or book, book, outstanding, deposits, 0, 0, period)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": "attachment; filename=bank_reconciliation.pdf"})




@app.get("/api/income")
def list_income(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return db.query(IncomeReceipt).filter(IncomeReceipt.company_id == current_user.company_id).order_by(IncomeReceipt.id.desc()).all()


@app.post("/api/income")
def create_income(
    received_from: str = Form(...),
    amount: float = Form(0),
    narration: str = Form(""),
    project_code_id: Optional[int] = Form(None),
    income_account_id: Optional[int] = Form(None),
    cash_account_id: Optional[int] = Form(None),
    lines_json: str = Form("[]"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    import json as _json
    lines = _json.loads(lines_json or "[]")
    total = sum(float(L.get("amount") or (float(L.get("quantity") or 0) * float(L.get("unit_cost") or 0))) for L in lines) if lines else float(amount)
    if total <= 0:
        raise HTTPException(400, "Amount must be greater than zero")
    n = db.query(IncomeReceipt).filter(IncomeReceipt.company_id == current_user.company_id).count() + 1
    rno = f"INC-{datetime.utcnow().strftime('%Y%m')}-{n:04d}"
    rec = IncomeReceipt(
        company_id=current_user.company_id, receipt_no=rno, received_from=received_from,
        amount=total, narration=narration, project_code_id=project_code_id,
        income_account_id=income_account_id, cash_account_id=cash_account_id,
        status="draft", created_by=current_user.id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    for i, L in enumerate(lines):
        amt = float(L.get("amount") or (float(L.get("quantity") or 0) * float(L.get("unit_cost") or 0)))
        db.add(IncomeReceiptLine(
            income_receipt_id=rec.id, description=L.get("description") or "Income line",
            quantity=float(L.get("quantity") or 1), unit_cost=float(L.get("unit_cost") or 0),
            amount=amt, sort_order=i,
        ))
    db.commit()
    return rec


@app.post("/api/income/{rid}/post")
def post_income(rid: int, current_user: User = Depends(require_roles("finance", "company_admin")), db: Session = Depends(get_db)):
    rec = db.query(IncomeReceipt).filter(IncomeReceipt.id == rid, IncomeReceipt.company_id == current_user.company_id).first()
    if not rec or rec.status == "posted":
        raise HTTPException(400, "Invalid receipt")
    if not rec.income_account_id or not rec.cash_account_id:
        raise HTTPException(400, "Set debit (cash/bank) and credit (income) accounts before posting")
    # Dr Cash, Cr Income
    post_double_entry(
        db, current_user.company_id, current_user.id,
        "income", rec.id,
        f"Income {rec.receipt_no}: {rec.received_from}",
        rec.narration or "",
        rec.cash_account_id, rec.income_account_id, rec.amount,
        project_code_id=rec.project_code_id,
    )
    rec.status = "posted"
    rec.posted_at = datetime.utcnow()
    db.commit()
    audit(db, current_user.company_id, current_user, "INCOME_POST", rec.receipt_no)
    return {"message": "Income posted to ledger", "status": rec.status}



FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

def _public_html(name: str):
    p = FRONTEND_DIR / "public" / name
    if p.exists():
        return FileResponse(str(p), media_type="text/html")
    return None

@app.get("/quote/{token}")
def vendor_quote_portal(token: str):
    """Standalone vendor quotation portal (no ERP chrome)."""
    resp = _public_html("quote.html")
    if resp:
        return resp
    raise HTTPException(404, "Vendor portal page missing on server")

@app.get("/po-result/{token}")
def vendor_po_result_portal(token: str):
    resp = _public_html("po-result.html")
    if resp:
        return resp
    raise HTTPException(404, "Result page missing")

@app.get("/committee-score/{token}")
def committee_score_portal(token: str):
    resp = _public_html("committee-score.html")
    if resp:
        return resp
    raise HTTPException(404, "Committee page missing")

@app.get("/")
def serve_index():
    index = FRONTEND_DIR / "index.html"
    return FileResponse(index) if index.exists() else {"msg": "API up"}

@app.get("/styles.css")
def serve_css():
    p = FRONTEND_DIR / "styles.css"
    return FileResponse(p) if p.exists() else HTTPException(404)

@app.get("/app.js")
def serve_js():
    p = FRONTEND_DIR / "app.js"
    return FileResponse(p) if p.exists() else HTTPException(404)

@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    # never swallow vendor portals
    if full_path.startswith("quote/") or full_path.startswith("po-result/") or full_path.startswith("committee-score/"):
        raise HTTPException(404, "Use the dedicated portal route")
    fp = FRONTEND_DIR / full_path
    if fp.exists() and fp.is_file():
        return FileResponse(fp)
    index = FRONTEND_DIR / "index.html"
    return FileResponse(index) if index.exists() else HTTPException(404)
