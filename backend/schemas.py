from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
import re

STRONG_PWD = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+=\[\]{};:,.<>?/\\|]).{10,}$"
)

def validate_strong_password(v: str) -> str:
    if not STRONG_PWD.match(v):
        raise ValueError(
            "Password must be at least 10 characters and include uppercase, lowercase, number, and special character"
        )
    return v


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class CompanyRegister(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=200)
    company_slug: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9\-]+$")
    address: Optional[str] = ""
    admin_username: str = Field(..., min_length=3, max_length=50)
    admin_email: EmailStr
    admin_full_name: Optional[str] = None
    admin_password: str = Field(..., min_length=10)

    @field_validator("admin_password")
    @classmethod
    def strong_pwd(cls, v):
        return validate_strong_password(v)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=10)

    @field_validator("new_password")
    @classmethod
    def strong_pwd(cls, v):
        return validate_strong_password(v)


class PasswordResetRequest(BaseModel):
    email: EmailStr
    company_slug: Optional[str] = None


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=10)

    @field_validator("new_password")
    @classmethod
    def strong_pwd(cls, v):
        return validate_strong_password(v)


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    role: str = "user"
    is_active: bool = True
    can_access_finance: bool = False
    can_access_inventory: bool = False
    can_access_assets: bool = False
    can_edit_assets: bool = False
    can_access_vendors: bool = False
    can_access_reports: bool = False
    can_approve_payment: bool = False


class UserCreate(UserBase):
    password: str = Field(..., min_length=10)

    @field_validator("password")
    @classmethod
    def strong_pwd(cls, v):
        return validate_strong_password(v)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    can_access_finance: Optional[bool] = None
    can_access_inventory: Optional[bool] = None
    can_access_assets: Optional[bool] = None
    can_edit_assets: Optional[bool] = None
    can_access_vendors: Optional[bool] = None
    can_access_reports: Optional[bool] = None
    can_approve_payment: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def strong_pwd(cls, v):
        if v is None:
            return v
        return validate_strong_password(v)


class UserOut(UserBase):
    id: int
    company_id: Optional[int] = None
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompanyOut(BaseModel):
    id: int
    name: str
    slug: str
    address: str
    project_code: str
    reporting_currency_code: str
    reporting_currency_symbol: str
    logo_path: str
    favicon_path: str
    status: str
    license_key: Optional[str] = None
    license_expires: Optional[date] = None
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    project_code: Optional[str] = None
    reporting_currency_code: Optional[str] = None
    reporting_currency_symbol: Optional[str] = None


class LicenseIssue(BaseModel):
    years: int = Field(1, ge=1, le=5)
    notes: Optional[str] = ""


class CompanySettingsOut(BaseModel):
    org_name: str
    logo_path: str
    favicon_path: str

    class Config:
        from_attributes = True


class COAIn(BaseModel):
    code: str
    name: str
    account_type: str = "Expense"
    project_code: str = ""


class BudgetCodeIn(BaseModel):
    code: str
    description: str = ""
    amount: float = 0.0
    default_approver_id: Optional[int] = None


class ExpenseCodeIn(BaseModel):
    code: str
    description: str
    budget_code_id: Optional[int] = None
    default_debit_account_id: Optional[int] = None
    default_credit_account_id: Optional[int] = None


class PaymentLineIn(BaseModel):
    description: str = ""
    quantity: float = 1
    unit_cost: float = 0
    amount: float = 0

class PaymentRequestIn(BaseModel):
    budget_code_id: int
    expense_code_id: int
    amount: float = Field(..., gt=0)
    narration: str = ""
    payee_name: str = ""
    debit_account_id: Optional[int] = None
    credit_account_id: Optional[int] = None
    designated_approver_id: int
    project_code_id: Optional[int] = None
    line_items: List[PaymentLineIn] = []
    amount_in_words: Optional[str] = None


class PaymentAction(BaseModel):
    comment: str = ""
    debit_account_id: Optional[int] = None
    credit_account_id: Optional[int] = None


class AssetIn(BaseModel):
    asset_number: str
    asset_name: str
    category: str = ""
    location: str = ""
    purchase_date: Optional[date] = None
    cost: float = 0.0
    depreciation_rate: float = 0.0
    useful_life: float = 0.0
    insurance: str = ""
    condition: str = "Good"
    nbv: float = 0.0
    notes: str = ""
    assigned_to: str = ""
    status: str = "active"
    debit_account_id: Optional[int] = None
    credit_account_id: Optional[int] = None
    project_code_id: Optional[int] = None
