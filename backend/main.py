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
    ChartOfAccount, BudgetCode, ExpenseCode, PaymentRequest, PaymentApprovalLog, Asset
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
        print("✅ Demo company approved + licensed | admin / Admin@Knowsoft1!")


@app.on_event("startup")
def on_startup():
    db = next(get_db())
    try:
        init_defaults(db)
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
    row = ChartOfAccount(company_id=current_user.company_id, code=data.code, name=data.name, account_type=data.account_type)
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
    pr.status = "paid"
    pr.paid_at = datetime.utcnow()
    bud = db.query(BudgetCode).filter(BudgetCode.id == pr.budget_code_id).first()
    if bud:
        bud.spent = (bud.spent or 0) + pr.amount
    db.add(PaymentApprovalLog(payment_request_id=pr.id, actor_id=current_user.id, action="pay", comment=data.comment))
    db.commit()
    return {"message": "Marked as paid", "status": pr.status}


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
