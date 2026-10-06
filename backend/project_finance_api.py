"""
Project-based finance & analysis API.
Budgets live under projects. Full financial analysis + chart data per project.
IFRS-oriented presentation classes used in responses.
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field

from database import get_db
from models import (
    User, Company, ProjectCode, BudgetCode, ExpenseCode,
    PaymentRequest, ChartOfAccount, PurchaseOrder,
)
from auth import get_current_active_user, check_company_license

router = APIRouter(prefix="/api/projects", tags=["Project Finance"])


# ---------- Schemas ----------
class ProjectIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    budget_amount: float = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    currency_code: str = "NGN"


class BudgetLineIn(BaseModel):
    code: str
    description: str = ""
    amount: float = Field(..., ge=0)
    ifrs_class: str = "Expense"  # Expense | Asset | etc.


class ProjectAnalysis(BaseModel):
    project_id: int
    code: str
    name: str
    budget_ceiling: float
    budget_allocated: float
    spent: float
    committed: float  # open POs
    remaining: float
    burn_rate_pct: float
    variance: float
    variance_pct: float
    by_category: List[Dict[str, Any]]
    monthly_trend: List[Dict[str, Any]]
    status: str


# ---------- Helpers ----------
def _company_user(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not user.company_id:
        raise HTTPException(403, "Company context required")
    check_company_license(db, user.company_id)
    return user


def _project_or_404(db: Session, company_id: int, project_id: int) -> ProjectCode:
    p = db.query(ProjectCode).filter(
        ProjectCode.id == project_id,
        ProjectCode.company_id == company_id,
    ).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


# ---------- CRUD ----------
@router.get("")
def list_projects(user: User = Depends(_company_user), db: Session = Depends(get_db)):
    rows = db.query(ProjectCode).filter(ProjectCode.company_id == user.company_id).order_by(ProjectCode.code).all()
    out = []
    for p in rows:
        spent = db.query(func.coalesce(func.sum(PaymentRequest.amount), 0.0)).filter(
            PaymentRequest.company_id == user.company_id,
            PaymentRequest.project_code_id == p.id,
            PaymentRequest.status == "paid",
        ).scalar() or 0.0
        allocated = db.query(func.coalesce(func.sum(BudgetCode.amount), 0.0)).filter(
            BudgetCode.company_id == user.company_id,
            getattr(BudgetCode, "project_code_id", None) == p.id if hasattr(BudgetCode, "project_code_id") else True,
        ).scalar() or 0.0
        # Fallback: match by project_code string if no FK
        if allocated == 0 and hasattr(p, "code"):
            allocated = float(getattr(p, "budget_amount", 0) or 0)
        out.append({
            "id": p.id,
            "code": p.code,
            "name": getattr(p, "name", p.code),
            "budget_amount": float(getattr(p, "budget_amount", 0) or 0),
            "spent": float(spent),
            "start_date": str(getattr(p, "start_date", "") or ""),
            "end_date": str(getattr(p, "end_date", "") or ""),
            "status": "active" if float(spent) < float(getattr(p, "budget_amount", 0) or 1e18) else "over",
        })
    return out


@router.post("")
def create_project(data: ProjectIn, user: User = Depends(_company_user), db: Session = Depends(get_db)):
    exists = db.query(ProjectCode).filter(
        ProjectCode.company_id == user.company_id,
        ProjectCode.code == data.code.strip().upper(),
    ).first()
    if exists:
        raise HTTPException(400, "Project code already exists")
    p = ProjectCode(
        company_id=user.company_id,
        code=data.code.strip().upper(),
        name=data.name.strip(),
        budget_amount=data.budget_amount,
        start_date=data.start_date,
        end_date=data.end_date,
    )
    if hasattr(p, "description"):
        p.description = data.description
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "code": p.code, "name": getattr(p, "name", p.code), "message": "Project created"}


@router.get("/{project_id}/analysis")
def project_analysis(project_id: int, user: User = Depends(_company_user), db: Session = Depends(get_db)):
    p = _project_or_404(db, user.company_id, project_id)
    ceiling = float(getattr(p, "budget_amount", 0) or 0)

    # Spent = paid payment requests on this project
    spent = float(db.query(func.coalesce(func.sum(PaymentRequest.amount), 0.0)).filter(
        PaymentRequest.company_id == user.company_id,
        PaymentRequest.project_code_id == p.id,
        PaymentRequest.status == "paid",
    ).scalar() or 0)

    # Committed = open POs linked to this project (if column exists)
    committed = 0.0
    try:
        committed = float(db.query(func.coalesce(func.sum(PurchaseOrder.amount), 0.0)).filter(
            PurchaseOrder.company_id == user.company_id,
            PurchaseOrder.project_code_id == p.id,
            PurchaseOrder.status.notin_(["cancelled", "paid", "closed"]),
        ).scalar() or 0)
    except Exception:
        pass

    remaining = ceiling - spent - committed
    burn = (spent / ceiling * 100) if ceiling > 0 else 0
    variance = ceiling - spent
    variance_pct = (variance / ceiling * 100) if ceiling > 0 else 0

    # By category (expense codes / narration buckets)
    by_cat_rows = db.query(
        func.coalesce(PaymentRequest.narration, "Other"),
        func.sum(PaymentRequest.amount),
    ).filter(
        PaymentRequest.company_id == user.company_id,
        PaymentRequest.project_code_id == p.id,
        PaymentRequest.status == "paid",
    ).group_by(PaymentRequest.narration).all()

    by_category = [{"label": (r[0] or "Other")[:40], "value": float(r[1] or 0)} for r in by_cat_rows]

    # Monthly trend
    monthly_rows = db.query(
        func.strftime("%Y-%m", PaymentRequest.paid_at),
        func.sum(PaymentRequest.amount),
    ).filter(
        PaymentRequest.company_id == user.company_id,
        PaymentRequest.project_code_id == p.id,
        PaymentRequest.status == "paid",
        PaymentRequest.paid_at.isnot(None),
    ).group_by(func.strftime("%Y-%m", PaymentRequest.paid_at)).order_by(func.strftime("%Y-%m", PaymentRequest.paid_at)).all()

    # SQLite strftime; for Postgres use date_trunc — keep simple fallback
    monthly_trend = []
    for r in monthly_rows:
        monthly_trend.append({"month": r[0] or "—", "spent": float(r[1] or 0)})
    if not monthly_trend:
        # Fallback without date grouping
        monthly_trend = [{"month": "Total", "spent": spent}]

    status = "on_track"
    if ceiling > 0 and spent > ceiling:
        status = "over_budget"
    elif ceiling > 0 and burn >= 85:
        status = "at_risk"

    return {
        "project_id": p.id,
        "code": p.code,
        "name": getattr(p, "name", p.code),
        "budget_ceiling": ceiling,
        "budget_allocated": ceiling,
        "spent": spent,
        "committed": committed,
        "remaining": remaining,
        "burn_rate_pct": round(burn, 1),
        "variance": round(variance, 2),
        "variance_pct": round(variance_pct, 1),
        "by_category": by_category,
        "monthly_trend": monthly_trend,
        "status": status,
        "ifrs_note": "Figures are in the company reporting currency. Presentation follows expense-by-nature for management reporting.",
    }


@router.get("/{project_id}/charts")
def project_charts(project_id: int, user: User = Depends(_company_user), db: Session = Depends(get_db)):
    """Chart.js-ready payloads for project dashboard."""
    analysis = project_analysis(project_id, user, db)
    return {
        "budget_vs_actual": {
            "labels": ["Budget", "Spent", "Committed", "Remaining"],
            "data": [
                analysis["budget_ceiling"],
                analysis["spent"],
                analysis["committed"],
                max(0, analysis["remaining"]),
            ],
        },
        "expense_breakdown": {
            "labels": [c["label"] for c in analysis["by_category"]] or ["No spend"],
            "data": [c["value"] for c in analysis["by_category"]] or [0],
        },
        "monthly_trend": {
            "labels": [m["month"] for m in analysis["monthly_trend"]],
            "data": [m["spent"] for m in analysis["monthly_trend"]],
        },
        "status": analysis["status"],
        "burn_rate_pct": analysis["burn_rate_pct"],
    }


# ---------- Currencies ----------
CURRENCIES = [
    {"code": "NGN", "symbol": "₦", "name": "Nigerian Naira"},
    {"code": "USD", "symbol": "$", "name": "US Dollar"},
    {"code": "EUR", "symbol": "€", "name": "Euro"},
    {"code": "GBP", "symbol": "£", "name": "British Pound"},
    {"code": "GHS", "symbol": "₵", "name": "Ghanaian Cedi"},
    {"code": "KES", "symbol": "KSh", "name": "Kenyan Shilling"},
    {"code": "ZAR", "symbol": "R", "name": "South African Rand"},
    {"code": "XOF", "symbol": "CFA", "name": "West African CFA Franc"},
    {"code": "CAD", "symbol": "C$", "name": "Canadian Dollar"},
    {"code": "CNY", "symbol": "¥", "name": "Chinese Yuan"},
]


@router.get("/meta/currencies")
def list_currencies():
    return CURRENCIES
