"""
General Admin API — approvals, licenses, technical corrections only.
Replaces the old "superadmin" surface with a clean platform-owner role.
"""
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# These imports match the existing project structure
from database import get_db
from models import User, Company, AuditLog
from auth import get_password_hash, create_access_token, verify_password, get_current_active_user

router = APIRouter(prefix="/api/general-admin", tags=["General Admin"])

GENERAL_ADMIN_USERNAME = "general_admin"
GENERAL_ADMIN_PASSWORD = "GeneralAdmin@FMSS2026!"
GENERAL_ADMIN_ROLE = "general_admin"


# ---------- Schemas ----------
class GALogin(BaseModel):
    username: str
    password: str


class CompanyOut(BaseModel):
    id: int
    name: str
    slug: str
    status: str
    license_expires: Optional[date] = None
    license_key: Optional[str] = None
    address: Optional[str] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

    class Config:
        from_attributes = True


class LicenseIn(BaseModel):
    years: int = Field(1, ge=1, le=5)
    notes: str = ""


class CorrectionNote(BaseModel):
    company_id: int
    title: str
    detail: str
    priority: str = "normal"  # low | normal | high


# ---------- Helpers ----------
def require_general_admin(user: User = Depends(get_current_active_user)) -> User:
    if user.role not in (GENERAL_ADMIN_ROLE, "superadmin", "owner"):
        raise HTTPException(403, "General Admin access only")
    if user.company_id is not None:
        raise HTTPException(403, "General Admin must be a platform account")
    return user


def ensure_general_admin(db: Session) -> User:
    """Seed or upgrade the platform General Admin account."""
    ga = db.query(User).filter(
        User.username == GENERAL_ADMIN_USERNAME,
        User.company_id.is_(None),
    ).first()
    if not ga:
        # Migrate old superadmin if present
        old = db.query(User).filter(
            User.username == "superadmin",
            User.company_id.is_(None),
        ).first()
        if old:
            old.username = GENERAL_ADMIN_USERNAME
            old.role = GENERAL_ADMIN_ROLE
            old.full_name = "Platform General Admin"
            old.hashed_password = get_password_hash(GENERAL_ADMIN_PASSWORD)
            old.email = "general_admin@knowsoft.local"
            db.add(old)
            db.commit()
            db.refresh(old)
            print("✅ Migrated superadmin → general_admin")
            return old
        ga = User(
            company_id=None,
            username=GENERAL_ADMIN_USERNAME,
            email="general_admin@knowsoft.local",
            full_name="Platform General Admin",
            hashed_password=get_password_hash(GENERAL_ADMIN_PASSWORD),
            role=GENERAL_ADMIN_ROLE,
            is_active=True,
            can_access_finance=False,
            can_access_inventory=False,
            can_access_assets=False,
            can_edit_assets=False,
            can_access_vendors=False,
            can_access_reports=False,
            can_approve_payment=False,
        )
        db.add(ga)
        db.commit()
        db.refresh(ga)
        print(f"✅ General Admin: {GENERAL_ADMIN_USERNAME} / {GENERAL_ADMIN_PASSWORD}")
    else:
        # Keep password in sync for demo environments
        ga.role = GENERAL_ADMIN_ROLE
        ga.hashed_password = get_password_hash(GENERAL_ADMIN_PASSWORD)
        db.add(ga)
        db.commit()
    return ga


def _audit(db: Session, company_id, user, action: str, details: str):
    db.add(AuditLog(
        company_id=company_id,
        user_id=user.id if user else None,
        username=user.username if user else "system",
        action=action,
        details=details,
    ))
    db.commit()


def _gen_license_key(slug: str) -> str:
    import secrets
    return f"KS-{slug.upper()[:8]}-{secrets.token_hex(4).upper()}"


# ---------- Auth ----------
@router.post("/login")
def general_admin_login(data: GALogin, db: Session = Depends(get_db)):
    ensure_general_admin(db)
    user = db.query(User).filter(
        User.username == data.username.strip(),
        User.company_id.is_(None),
        User.role.in_([GENERAL_ADMIN_ROLE, "superadmin", "owner"]),
    ).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid General Admin credentials")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": GENERAL_ADMIN_ROLE,
            "company_id": None,
            "company_name": "Knowsoft Platform",
            "is_general_admin": True,
        },
    }


# ---------- Companies (approval surface) ----------
@router.get("/companies", response_model=List[CompanyOut])
def list_companies(
    status: Optional[str] = None,
    user: User = Depends(require_general_admin),
    db: Session = Depends(get_db),
):
    q = db.query(Company)
    if status:
        q = q.filter(Company.status == status)
    return q.order_by(Company.id.desc()).all()


@router.post("/companies/{company_id}/approve")
def approve_company(
    company_id: int,
    user: User = Depends(require_general_admin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    co.status = "approved"
    co.approved_at = datetime.utcnow()
    co.approved_by = user.username
    if not co.license_key:
        co.license_key = _gen_license_key(co.slug)
    if not co.license_expires or co.license_expires < date.today():
        co.license_expires = date.today() + timedelta(days=365)
    db.commit()
    _audit(db, co.id, user, "APPROVE_COMPANY", f"Approved {co.name}")
    return {
        "message": f"{co.name} approved",
        "license_key": co.license_key,
        "license_expires": str(co.license_expires),
        "status": co.status,
    }


@router.post("/companies/{company_id}/reject")
def reject_company(
    company_id: int,
    user: User = Depends(require_general_admin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    co.status = "rejected"
    db.commit()
    _audit(db, co.id, user, "REJECT_COMPANY", f"Rejected {co.name}")
    return {"message": f"{co.name} rejected", "status": "rejected"}


@router.post("/companies/{company_id}/suspend")
def suspend_company(
    company_id: int,
    user: User = Depends(require_general_admin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    co.status = "suspended"
    db.commit()
    _audit(db, co.id, user, "SUSPEND_COMPANY", f"Suspended {co.name}")
    return {"message": f"{co.name} suspended", "status": "suspended"}


@router.post("/companies/{company_id}/license")
def issue_license(
    company_id: int,
    data: LicenseIn,
    user: User = Depends(require_general_admin),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        raise HTTPException(404, "Company not found")
    if co.status != "approved":
        co.status = "approved"
        co.approved_at = datetime.utcnow()
        co.approved_by = user.username
    co.license_key = _gen_license_key(co.slug)
    base = co.license_expires if co.license_expires and co.license_expires > date.today() else date.today()
    co.license_expires = base + timedelta(days=365 * data.years)
    if hasattr(co, "license_notes"):
        co.license_notes = data.notes or ""
    db.commit()
    _audit(db, co.id, user, "ISSUE_LICENSE", f"{data.years} year(s) until {co.license_expires}")
    return {
        "message": "License issued",
        "license_key": co.license_key,
        "license_expires": str(co.license_expires),
    }


# ---------- Technical corrections (platform view) ----------
@router.get("/corrections")
def list_corrections(
    user: User = Depends(require_general_admin),
    db: Session = Depends(get_db),
):
    """List open technical correction requests across all companies (if model exists)."""
    try:
        from models import CorrectionRequest
        rows = db.query(CorrectionRequest).order_by(CorrectionRequest.id.desc()).limit(100).all()
        return [
            {
                "id": r.id,
                "company_id": r.company_id,
                "title": getattr(r, "title", "") or getattr(r, "message", ""),
                "status": getattr(r, "status", "open"),
                "created_at": str(getattr(r, "created_at", "")),
            }
            for r in rows
        ]
    except Exception:
        return []


@router.get("/health")
def ga_health():
    return {"role": "general_admin", "ok": True}
