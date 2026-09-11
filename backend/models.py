from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, Float,
    ForeignKey, UniqueConstraint, Date
)
from sqlalchemy.orm import relationship
from datetime import datetime, date
from database import Base


class Company(Base):
    """Tenant firm. Must be approved by superadmin and hold a valid annual license."""
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    address = Column(Text, default="")
    project_code = Column(String(50), default="")
    reporting_currency_code = Column(String(10), default="NGN")
    reporting_currency_symbol = Column(String(10), default="₦")
    logo_path = Column(String(500), default="/static/images/logo.png")
    favicon_path = Column(String(500), default="/static/images/favicon.ico")
    # pending | approved | suspended | rejected
    status = Column(String(20), default="pending", index=True)
    license_key = Column(String(100), nullable=True)
    license_expires = Column(Date, nullable=True)
    license_notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String(50), nullable=True)

    users = relationship("User", back_populates="company")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("company_id", "username", name="uq_company_username"),
        UniqueConstraint("company_id", "email", name="uq_company_email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # company_id NULL only for platform superadmin
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    username = Column(String(50), nullable=False, index=True)
    email = Column(String(100), nullable=False, index=True)
    full_name = Column(String(100))
    hashed_password = Column(String(255), nullable=False)
    # superadmin | company_admin | finance | program | project_manager | asset_editor | user
    role = Column(String(30), default="user")
    is_active = Column(Boolean, default=True)
    must_reset_password = Column(Boolean, default=False)
    can_access_finance = Column(Boolean, default=False)
    can_access_inventory = Column(Boolean, default=False)
    can_access_assets = Column(Boolean, default=False)
    can_edit_assets = Column(Boolean, default=False)
    can_access_vendors = Column(Boolean, default=False)
    can_access_reports = Column(Boolean, default=False)
    can_approve_payment = Column(Boolean, default=False)
    signature_path = Column(String(500), nullable=True)  # uploaded signature image for vouchers
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    company = relationship("Company", back_populates="users")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(100), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(50))
    action = Column(String(100))
    details = Column(Text)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id = Column(Integer, primary_key=True, index=True)
    org_name = Column(String(200), default="Knowsoft FMSS ERP")
    logo_path = Column(String(500), default="/static/images/logo.png")
    favicon_path = Column(String(500), default="/static/images/favicon.ico")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChartOfAccount(Base):
    __tablename__ = "chart_of_accounts"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_coa_code"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    account_type = Column(String(50), default="Expense")  # Asset, Liability, Equity, Income, Expense, Cash
    project_code = Column(String(50), default="")  # optional project code tag on account
    is_active = Column(Boolean, default=True)


class BudgetCode(Base):

    __tablename__ = "budget_codes"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_budget_code"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    description = Column(String(300), default="")
    amount = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    # default approver user id for this budget line
    default_approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class ExpenseCode(Base):
    """Finance ties each expense code to default debit & credit accounts."""
    __tablename__ = "expense_codes"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_expense_code"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    description = Column(String(300), nullable=False)
    budget_code_id = Column(Integer, ForeignKey("budget_codes.id"), nullable=True)
    default_debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    default_credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)


class PaymentRequest(Base):
    """Payment request workflow: submit → program → finance → payment."""
    __tablename__ = "payment_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    request_no = Column(String(50), nullable=False, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    budget_code_id = Column(Integer, ForeignKey("budget_codes.id"), nullable=False)
    expense_code_id = Column(Integer, ForeignKey("expense_codes.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="NGN")
    narration = Column(Text, default="")
    payee_name = Column(String(200), default="")
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    # optional user selection; finance can override before final approval
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    # who must approve this budget line (selected by requester)
    designated_approver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # draft | submitted | program_approved | finance_approved | paid | rejected | returned
    status = Column(String(30), default="submitted", index=True)
    program_approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    program_approved_at = Column(DateTime, nullable=True)
    finance_approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    finance_approved_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, default="")
    return_comment = Column(Text, default="")
    returned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentApprovalLog(Base):
    __tablename__ = "payment_approval_logs"

    id = Column(Integer, primary_key=True, index=True)
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50))  # submit, program_approve, finance_approve, reject, pay
    comment = Column(Text, default="")
    debit_account_id = Column(Integer, nullable=True)
    credit_account_id = Column(Integer, nullable=True)
    amount_snapshot = Column(Float, nullable=True)
    details_json = Column(Text, default="")  # full snapshot for audit trail
    created_at = Column(DateTime, default=datetime.utcnow)


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    asset_number = Column(String(50), nullable=False)
    asset_name = Column(String(200), nullable=False)
    category = Column(String(100), default="")
    location = Column(String(200), default="")
    purchase_date = Column(Date, nullable=True)
    cost = Column(Float, default=0.0)
    depreciation_rate = Column(Float, default=0.0)
    useful_life = Column(Float, default=0.0)
    insurance = Column(String(50), default="")
    condition = Column(String(50), default="Good")
    nbv = Column(Float, default=0.0)
    image_path = Column(String(500), nullable=True)
    notes = Column(Text, default="")
    assigned_to = Column(String(150), default="")
    status = Column(String(30), default="active")  # active | under_repair | disposed
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    disposed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class PaymentAttachment(Base):
    __tablename__ = "payment_attachments"

    id = Column(Integer, primary_key=True, index=True)
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    content_type = Column(String(100), default="application/octet-stream")
    size_bytes = Column(Integer, default=0)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProjectCode(Base):
    __tablename__ = "project_codes"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_project_code"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True)


class JournalEntry(Base):
    """General ledger journal line — all modules post here."""
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    entry_no = Column(String(50), nullable=False, index=True)
    entry_date = Column(Date, default=date.today)
    source_type = Column(String(40), default="")  # payment, asset, inventory, vendor, manual, asset_adjustment
    source_id = Column(Integer, nullable=True)
    account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    description = Column(String(300), default="")
    narration = Column(Text, default="")
    debit = Column(Float, default=0.0)
    credit = Column(Float, default=0.0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("company_id", "item_code", name="uq_inv_code"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    item_code = Column(String(50), nullable=False)
    item_name = Column(String(200), nullable=False)
    category = Column(String(100), default="")
    note = Column(Text, default="")
    department = Column(String(100), default="")
    cost_price = Column(Float, default=0.0)
    qty_received = Column(Float, default=0.0)
    qty_issued = Column(Float, default=0.0)
    balance_qty = Column(Float, default=0.0)
    total_value = Column(Float, default=0.0)
    receive_method = Column(String(100), default="")
    funding_source = Column(String(100), default="")
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    movement_type = Column(String(20), default="receive")  # receive | issue | adjust
    quantity = Column(Float, default=0.0)
    unit_cost = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    narration = Column(Text, default="")
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("company_id", "vendor_number", name="uq_vendor_no"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    vendor_number = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    address = Column(Text, default="")
    cac_number = Column(String(100), default="")
    experience = Column(String(100), default="")
    tax_clearance = Column(String(50), default="")
    bank = Column(String(150), default="")
    reg_with_govt = Column(String(50), default="")
    audit_3yrs = Column(String(50), default="")
    description = Column(Text, default="")
    amount = Column(Float, default=0.0)
    score = Column(Float, default=0.0)
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AssetAccountingEntry(Base):
    """Finance posts value adjustments (add/reduce NBV) with debit/credit."""
    __tablename__ = "asset_accounting_entries"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    entry_date = Column(Date, default=date.today)
    description = Column(String(300), default="")
    narration = Column(Text, default="")
    amount = Column(Float, default=0.0)  # positive = increase NBV, negative = decrease
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    journal_entry_no = Column(String(50), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BankReconState(Base):
    """Persistent tick state for bank reconciliation lines."""
    __tablename__ = "bank_recon_states"
    __table_args__ = (UniqueConstraint("company_id", "journal_entry_id", name="uq_recon_je"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False, index=True)
    ticked = Column(Boolean, default=False)
    ticked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    ticked_at = Column(DateTime, nullable=True)
    note = Column(Text, default="")


class CorrectionRequest(Base):
    """Message to staff to correct a transaction; trail investigation."""
    __tablename__ = "correction_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    source_type = Column(String(40), default="")
    source_id = Column(Integer, nullable=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="open")  # open | resolved | dismissed
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class BankStatementSession(Base):
    """Bank statement balance entered for a recon period."""
    __tablename__ = "bank_statement_sessions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    statement_balance = Column(Float, default=0.0)
    book_balance = Column(Float, default=0.0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RFQ(Base):
    """Request for Quotation — procurement officer creates; vendors quote via expiring links."""
    __tablename__ = "rfqs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    rfq_no = Column(String(50), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    deadline = Column(DateTime, nullable=False)
    status = Column(String(30), default="open")  # open | closed | evaluated | awarded | cancelled
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    winner_quote_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RFQLineItem(Base):
    __tablename__ = "rfq_line_items"
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    description = Column(String(400), nullable=False)
    quantity = Column(Float, default=1.0)
    unit = Column(String(50), default="unit")
    conditions = Column(Text, default="")
    sort_order = Column(Integer, default=0)


class RFQQuoteLink(Base):

    """Unique link sent to a vendor to submit a quote; expires after deadline or when marked received."""
    __tablename__ = "rfq_quote_links"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    vendor_name = Column(String(200), default="")
    vendor_email = Column(String(150), default="")
    status = Column(String(30), default="pending")  # pending | submitted | received | expired
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    received_at = Column(DateTime, nullable=True)
    received_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class RFQQuote(Base):
    __tablename__ = "rfq_quotes"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    link_id = Column(Integer, ForeignKey("rfq_quote_links.id"), nullable=True)
    vendor_name = Column(String(200), nullable=False)
    vendor_email = Column(String(150), default="")
    vendor_phone = Column(String(50), default="")
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="NGN")
    validity_days = Column(Integer, default=30)
    notes = Column(Text, default="")
    attachment_path = Column(String(500), nullable=True)
    status = Column(String(30), default="submitted")  # submitted | received | scored | winner | rejected
    total_score = Column(Float, default=0.0)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    received_at = Column(DateTime, nullable=True)


class RFQCommitteeMember(Base):
    __tablename__ = "rfq_committee_members"
    __table_args__ = (UniqueConstraint("rfq_id", "user_id", name="uq_rfq_member"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_label = Column(String(100), default="Member")


class RFQCommitteeInvite(Base):
    """Link for committee member (existing staff or invited) to score quotes."""
    __tablename__ = "rfq_committee_invites"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    invite_email = Column(String(150), default="")
    invite_name = Column(String(200), default="")
    token = Column(String(64), unique=True, nullable=False, index=True)
    submitted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RFQQuoteScore(Base):

    __tablename__ = "rfq_quote_scores"
    __table_args__ = (UniqueConstraint("quote_id", "member_id", name="uq_quote_score"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("rfq_quotes.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    score = Column(Float, nullable=False)  # 0-100
    comments = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    po_no = Column(String(50), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=True)
    quote_id = Column(Integer, ForeignKey("rfq_quotes.id"), nullable=True)
    vendor_name = Column(String(200), nullable=False)
    vendor_email = Column(String(150), default="")
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="NGN")
    description = Column(Text, default="")
    # draft | pending_vendor | accepted | rejected | sent_to_finance | paid
    status = Column(String(30), default="draft")
    result_token = Column(String(64), unique=True, nullable=True, index=True)
    vendor_response = Column(String(20), default="")  # accepted | rejected | ""
    vendor_response_at = Column(DateTime, nullable=True)
    invoice_path = Column(String(500), nullable=True)
    delivery_percent = Column(Float, default=0.0)
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=True)
    designated_approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ===================== PROCUREMENT / RFQ =====================

class PaymentLine(Base):
    """Line items on a payment request: qty × unit cost = amount."""
    __tablename__ = "payment_lines"

    id = Column(Integer, primary_key=True, index=True)
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=False, index=True)
    description = Column(String(400), nullable=False)
    quantity = Column(Float, default=1.0)
    unit_cost = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    sort_order = Column(Integer, default=0)
