"""Standard ERP extensions: multi-currency, owner approval, robust tasks."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_active_user, get_password_hash
from database import get_db
from models import Company, Currency, ErpTask, ExchangeRate, User

router = APIRouter(prefix="/api/erp", tags=["erp"])

TRANSITIONS = {
    "draft": {"submit"},
    "submitted": {"assign", "reject"},
    "assigned": {"start", "reject"},
    "in_progress": {"complete", "fail", "hold"},
    "hold": {"start", "reject"},
    "failed": {"retry", "reject"},
    "complete": {"close"},
    "rejected": set(),
    "closed": set(),
}
ACTION_STATUS = {
    "submit": "submitted",
    "assign": "assigned",
    "start": "in_progress",
    "complete": "complete",
    "fail": "failed",
    "hold": "hold",
    "retry": "in_progress",
    "reject": "rejected",
    "close": "closed",
}


class RateIn(BaseModel):
    base_code: str
    quote_code: str
    rate: float = Field(gt=0)
    rate_date: date | None = None


class TaskIn(BaseModel):
    company_id: int | None = None
    task_type: str
    title: str
    priority: str = "normal"
    payload: dict = {}
    idempotency_key: str | None = None


class TaskAction(BaseModel):
    action: str
    note: str = ""


def _money(amount: float, places: int = 2) -> float:
    q = Decimal("1").scaleb(-places)
    return float(Decimal(str(amount)).quantize(q, rounding=ROUND_HALF_UP))


def require_owner(user: User = Depends(get_current_active_user)) -> User:
    if user.role not in ("owner", "superadmin") or user.company_id is not None:
        raise HTTPException(403, "Owner backend login required")
    return user


def seed_erp(db: Session) -> None:
    owner = db.query(User).filter(User.username == "owner", User.company_id.is_(None)).first()
    if not owner:
        db.add(User(
            company_id=None,
            username="owner",
            email="owner@knowsoft.local",
            full_name="Platform Owner",
            hashed_password=get_password_hash("Owner@FMSS2026!"),
            role="owner",
            is_active=True,
            can_access_finance=True,
            can_access_reports=True,
            can_approve_payment=True,
        ))
        db.commit()
    books = [
        ("NGN", "Nigerian Naira", "₦", True),
        ("USD", "US Dollar", "$", False),
        ("GBP", "British Pound", "£", False),
        ("EUR", "Euro", "€", False),
        ("GHS", "Ghanaian Cedi", "₵", False),
    ]
    for code, name, symbol, base in books:
        if not db.query(Currency).filter(Currency.code == code).first():
            db.add(Currency(code=code, name=name, symbol=symbol, is_base=base))
    db.commit()
    today = date.today()
    rates = [("USD", "NGN", 1550), ("GBP", "NGN", 1980), ("EUR", "NGN", 1680), ("GHS", "NGN", 105), ("NGN", "NGN", 1)]
    for base, quote, rate in rates:
        exists = db.query(ExchangeRate).filter(
            ExchangeRate.base_code == base, ExchangeRate.quote_code == quote, ExchangeRate.rate_date == today
        ).first()
        if not exists:
            db.add(ExchangeRate(base_code=base, quote_code=quote, rate=rate, rate_date=today, source="demo"))
    db.commit()
    pending = db.query(Company).filter(Company.slug == "harbour-trust").first()
    if not pending:
        pending = Company(name="Harbour Trust Foundation", slug="harbour-trust", address="Accra, Ghana", status="pending")
        db.add(pending)
        db.commit()
        db.refresh(pending)
        db.add(User(
            company_id=pending.id,
            username="admin",
            email="admin@harbour.local",
            full_name="Harbour Admin",
            hashed_password=get_password_hash("Harbour@Admin2026!"),
            role="company_admin",
            is_active=True,
        ))
        db.commit()
    open_task = db.query(ErpTask).filter(ErpTask.idempotency_key == "approve-harbour-trust").first()
    if not open_task:
        db.add(ErpTask(
            company_id=pending.id,
            task_type="company_approval",
            title="Approve Harbour Trust Foundation",
            status="submitted",
            assigned_role="owner",
            payload_json=json.dumps({"slug": "harbour-trust"}),
            idempotency_key="approve-harbour-trust",
            created_by="seed",
        ))
        db.commit()
    demo = db.query(Company).filter(Company.slug == "demo").first()
    if demo and not db.query(ErpTask).filter(ErpTask.idempotency_key == "fx-demo-usd").first():
        db.add(ErpTask(
            company_id=demo.id,
            task_type="fx_payment",
            title="Post USD 2,400 workshop fees at today's NGN rate",
            status="submitted",
            assigned_role="finance",
            payload_json=json.dumps({"currency": "USD", "amount": 2400, "payee": "Global Training Ltd"}),
            idempotency_key="fx-demo-usd",
            created_by="seed",
        ))
        db.add(ErpTask(
            company_id=demo.id,
            task_type="fx_payment",
            title="Post GBP 1,800 audit fee at today's NGN rate",
            status="assigned",
            assigned_role="finance",
            payload_json=json.dumps({"currency": "GBP", "amount": 1800, "payee": "London Audit LLP"}),
            idempotency_key="fx-demo-gbp",
            created_by="seed",
        ))
        db.commit()


def _rate(db: Session, base: str, quote: str) -> float:
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return 1.0
    row = db.query(ExchangeRate).filter(
        ExchangeRate.base_code == base, ExchangeRate.quote_code == quote
    ).order_by(ExchangeRate.rate_date.desc()).first()
    if row:
        return float(row.rate)
    inverse = db.query(ExchangeRate).filter(
        ExchangeRate.base_code == quote, ExchangeRate.quote_code == base
    ).order_by(ExchangeRate.rate_date.desc()).first()
    if inverse and inverse.rate:
        return 1 / float(inverse.rate)
    raise HTTPException(400, f"No exchange rate for {base}/{quote}")


@router.get("/currencies")
def currencies(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(Currency).filter(Currency.is_active == True).order_by(Currency.code).all()
    rates = db.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).limit(30).all()
    return {
        "currencies": [{"code": c.code, "name": c.name, "symbol": c.symbol, "is_base": c.is_base} for c in rows],
        "rates": [{"base": r.base_code, "quote": r.quote_code, "rate": r.rate, "date": str(r.rate_date)} for r in rates],
    }


@router.post("/rates")
def add_rate(data: RateIn, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    row = ExchangeRate(
        base_code=data.base_code.upper(),
        quote_code=data.quote_code.upper(),
        rate=data.rate,
        rate_date=data.rate_date or date.today(),
        source="owner",
    )
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id}


@router.get("/convert")
def convert(amount: float, from_code: str, to_code: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if amount < 0:
        raise HTTPException(400, "Amount cannot be negative")
    rate = _rate(db, from_code, to_code)
    return {"amount": amount, "from": from_code.upper(), "to": to_code.upper(), "rate": rate, "converted": _money(amount * rate)}


@router.get("/owner/companies")
def owner_companies(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    rows = db.query(Company).order_by(Company.created_at.desc()).all()
    return [{
        "id": c.id, "name": c.name, "slug": c.slug, "status": c.status,
        "address": c.address, "created_at": str(c.created_at),
    } for c in rows]


@router.post("/owner/companies/{company_id}/approve")
def owner_approve(company_id: int, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    if company.status == "approved":
        return {"ok": True, "status": "approved", "idempotent": True}
    if company.status == "rejected":
        raise HTTPException(400, "Rejected company cannot be approved without a new registration")
    company.status = "approved"
    company.is_active = True
    company.approved_at = datetime.utcnow()
    company.approved_by = user.username
    company.license_expires = date.today() + timedelta(days=365)
    task = db.query(ErpTask).filter(ErpTask.company_id == company.id, ErpTask.task_type == "company_approval").first()
    if task and task.status not in ("closed", "rejected"):
        task.status = "closed"
        task.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "status": company.status, "slug": company.slug}


@router.post("/owner/companies/{company_id}/reject")
def owner_reject(company_id: int, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    company.status = "rejected"
    company.is_active = False
    db.commit()
    return {"ok": True, "status": company.status}


@router.get("/tasks")
def list_tasks(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    q = db.query(ErpTask)
    if user.role not in ("owner", "superadmin"):
        q = q.filter(ErpTask.company_id == user.company_id)
    rows = q.order_by(ErpTask.id.desc()).limit(100).all()
    return [{
        "id": t.id, "title": t.title, "type": t.task_type, "status": t.status,
        "priority": t.priority, "attempts": t.attempts, "error": t.error, "company_id": t.company_id,
    } for t in rows]


@router.post("/tasks")
def create_task(data: TaskIn, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if data.idempotency_key:
        existing = db.query(ErpTask).filter(ErpTask.idempotency_key == data.idempotency_key).first()
        if existing:
            return {"ok": True, "id": existing.id, "status": existing.status, "idempotent": True}
    task = ErpTask(
        company_id=data.company_id or user.company_id,
        task_type=data.task_type.strip()[:40] or "general",
        title=data.title.strip()[:200],
        status="draft",
        priority=data.priority,
        payload_json=json.dumps(data.payload or {}),
        idempotency_key=data.idempotency_key,
        created_by=user.username,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"ok": True, "id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/act")
def act_task(task_id: int, data: TaskAction, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    task = db.query(ErpTask).filter(ErpTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    action = (data.action or "").strip().lower()
    allowed = TRANSITIONS.get(task.status, set())
    if action not in allowed:
        raise HTTPException(400, f"Cannot {action} a task in status {task.status}. Allowed: {sorted(allowed) or ['none']}")
    try:
        task.attempts = int(task.attempts or 0) + 1
        task.status = ACTION_STATUS[action]
        task.error = "" if action != "fail" else (data.note or "marked failed")
        task.updated_at = datetime.utcnow()
        if action == "complete" and task.task_type == "company_approval" and task.company_id:
            company = db.query(Company).filter(Company.id == task.company_id).first()
            if company and company.status == "pending":
                company.status = "approved"
                company.approved_by = user.username
                company.approved_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Task update failed safely: {exc}")
    return {"ok": True, "id": task.id, "status": task.status, "attempts": task.attempts}
