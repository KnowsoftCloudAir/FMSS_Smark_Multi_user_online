from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from pathlib import Path
import os, shutil, re, json, zipfile, io, csv, secrets

from database import engine, get_db, Base
from models import (
    User, Company, AuditLog, CompanySettings, PasswordResetToken,
    ChartOfAccount, BudgetCode, ExpenseCode, PaymentRequest, PaymentApprovalLog, Asset,
    PaymentAttachment, ProjectCode, JournalEntry, InventoryItem, InventoryMovement,
    Vendor, AssetAccountingEntry
)
from schemas import (
    Token, UserCreate, UserUpdate, UserOut, CompanyRegister, CompanyOut, CompanyUpdate,
    LicenseIssue, PasswordChange, PasswordResetRequest, PasswordResetConfirm,
    COAIn, BudgetCodeIn, ExpenseCodeIn, PaymentRequestIn, PaymentAction, AssetIn,
    CompanySettingsOut
)
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

    pr = PaymentRequest(
        company_id=current_user.company_id,
        request_no=next_request_no(db, current_user.company_id),
        requester_id=current_user.id,
        budget_code_id=data.budget_code_id,
        expense_code_id=data.expense_code_id,
        amount=data.amount,
        narration=data.narration,
        payee_name=data.payee_name,
        debit_account_id=debit_id,
        credit_account_id=credit_id,
        designated_approver_id=data.designated_approver_id,
        status="submitted",
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=current_user.id, action="submit", comment="Submitted"))
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
        out.append({
            "id": p.id, "request_no": p.request_no, "amount": p.amount, "status": p.status,
            "payee_name": p.payee_name, "narration": p.narration,
            "expense_code": exp.code if exp else None,
            "expense_description": exp.description if exp else None,
            "budget_code": bud.code if bud else None,
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
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == pid, PaymentRequest.company_id == current_user.company_id).first()
    if not pr or pr.status != "program_approved":
        raise HTTPException(400, "Request not awaiting finance approval")
    # Finance must ensure accounts
    if data.debit_account_id:
        pr.debit_account_id = data.debit_account_id
    if data.credit_account_id:
        pr.credit_account_id = data.credit_account_id
    if not pr.debit_account_id or not pr.credit_account_id:
        raise HTTPException(400, "Finance must set debit and credit accounts before approval")
    pr.status = "finance_approved"
    pr.finance_approved_by = current_user.id
    pr.finance_approved_at = datetime.utcnow()
    db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=current_user.id, action="finance_approve", comment=data.comment))
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
    atts = db.query(PaymentAttachment).filter(PaymentAttachment.payment_request_id == pr.id).all()
    logs = db.query(PaymentApprovalLog).filter(PaymentApprovalLog.payment_request_id == pr.id).order_by(PaymentApprovalLog.created_at).all()
    return {
        "id": pr.id, "request_no": pr.request_no, "amount": pr.amount, "status": pr.status,
        "payee_name": pr.payee_name, "narration": pr.narration, "currency": pr.currency,
        "budget_code": bud.code if bud else None, "budget_description": bud.description if bud else None,
        "expense_code": exp.code if exp else None, "expense_description": exp.description if exp else None,
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
        "attachments": [{"id": a.id, "filename": a.filename, "size_bytes": a.size_bytes, "url": a.stored_path} for a in atts],
        "history": [{"action": l.action, "comment": l.comment, "at": l.created_at.isoformat() if l.created_at else None} for l in logs],
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


FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@app.get("/")
def serve_index():
    index = FRONTEND_DIR / "index.html"
    return FileResponse(index) if index.exists() else {"msg": "API up"}

@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    fp = FRONTEND_DIR / full_path
    if fp.exists() and fp.is_file():
        return FileResponse(fp)
    index = FRONTEND_DIR / "index.html"
    return FileResponse(index) if index.exists() else HTTPException(404)
