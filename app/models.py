from sqlmodel import SQLModel, Field, Column, Text
from typing import Optional
from datetime import datetime, date
from sqlalchemy import Column as SAColumn, Text as SAText


class PlatformAdmin(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = ""
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Business(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    business_type: str = "Retail"
    cac_number: str = ""
    email: str = Field(index=True)
    phone: str = Field(index=True)
    bank_name: str = ""
    account_number: str = ""
    account_name: str = ""
    product_types: str = ""  # comma-separated
    logo_path: str = ""
    theme: str = "royal"  # royal | emerald | sunset | midnight
    receipt_style: str = "classic"  # classic | bold | minimal | branded
    payment_instructions: str = ""  # shown on showcase for buyers
    settings_password_hash: str = ""  # protects Settings; default payme1 until changed
    status: str = "pending"  # pending | approved | suspended
    approval_code: str = ""
    approval_code_used: bool = False
    subscription_status: str = "trial"  # trial | active | expired
    subscription_expires: Optional[date] = None
    monthly_fee: float = 5000.0
    subscription_price: float = 5000.0  # admin can override per business
    subscription_days: int = 30  # duration when payment confirmed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, foreign_key="business.id", index=True)
    username: str = Field(index=True)
    email: str = ""
    phone: str = ""
    full_name: str = ""
    hashed_password: str
    role: str = "owner"  # owner | staff | admin
    is_active: bool = True
    must_change_password: bool = True
    first_login_done: bool = False
    user_kind: str = "registered"  # demo | registered
    last_login_at: Optional[datetime] = None
    login_count: int = 0
    last_ip: str = ""
    last_user_agent: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    name: str
    sku_code: str = Field(index=True)  # unique per business
    description: str = ""
    quantity: float = 0.0
    opening_qty: float = 0.0  # stock at period / create
    brought_in: float = 0.0   # restocked since opening
    cost_price: float = 0.0
    profit_margin_pct: float = 20.0
    selling_price: float = 0.0
    barcode_path: str = ""
    image_url: str = ""  # Google Drive or external image link
    category: str = "General"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Sale(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    receipt_no: str = Field(index=True)
    payment_method: str = "cash"  # cash | credit
    total_amount: float = 0.0
    total_cost: float = 0.0
    amount_in_words: str = ""
    customer_name: str = ""
    customer_phone: str = ""
    notes: str = ""
    sales_rep_code: str = ""
    created_by: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SaleItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sale_id: int = Field(foreign_key="sale.id", index=True)
    product_id: Optional[int] = None
    product_name: str = ""
    sku_code: str = ""
    quantity: float = 1.0
    unit_cost: float = 0.0
    unit_price: float = 0.0
    line_total: float = 0.0


class Purchase(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    supplier: str = ""
    payment_method: str = "cash"  # cash | credit
    total_amount: float = 0.0
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Expense(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    category: str = "General"  # rent, utilities, salaries, transport, other
    description: str = ""
    amount: float = 0.0
    payment_method: str = "cash"
    expense_date: date = Field(default_factory=date.today)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CatalogLink(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    token: str = Field(index=True, unique=True)
    expires_at: datetime
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CustomerOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    catalog_link_id: Optional[int] = None
    customer_name: str = ""
    customer_phone: str = ""
    customer_address: str = ""
    items_json: str = "[]"
    total_amount: float = 0.0
    payment_consent: bool = False
    evidence_path: str = ""
    evidence_expires: Optional[datetime] = None
    status: str = "pending"  # pending | confirmed | fulfilled | cancelled | rejected | closed
    edit_reason: str = ""  # seller note when requesting customer reorder
    reorder_token: str = ""  # unique link token for customer to reorder
    parent_order_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SubscriptionPayment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    amount: float = 0.0
    method: str = "bank"
    reference: str = ""
    evidence_path: str = ""
    status: str = "pending"  # pending | confirmed
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlatformSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    monthly_fee: float = 5000.0
    currency: str = "NGN"
    bank_name: str = "Knowsoft Collections"
    account_number: str = "0123456789"
    account_name: str = "Knowsoft BizPOS"
    support_email: str = "support@knowsoft.local"
    app_download_url: str = ""


class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = None
    user_id: Optional[int] = None
    name: str = ""
    email: str = ""
    message: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PasswordResetCode(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    admin_id: Optional[int] = None  # platform admin reset
    code: str = Field(index=True)
    used: bool = False
    expires_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SalesRep(SQLModel, table=True):
    """Codes that unlock Scan & Sell for a business."""
    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    code: str = Field(index=True)
    name: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserActivity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    business_id: Optional[int] = Field(default=None, index=True)
    username: str = ""
    action: str = ""
    detail: str = ""
    ip: str = ""
    user_agent: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
