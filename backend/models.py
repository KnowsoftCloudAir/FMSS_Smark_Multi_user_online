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
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    amount = Column(Float, nullable=False)
    amount_in_words = Column(String(500), default="")
    currency = Column(String(10), default="NGN")
    narration = Column(Text, default="")
    line_items_json = Column(Text, default="[]")  # [{desc, qty, unit_cost, amount}]
    payee_name = Column(String(200), default="")
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentLineItem(Base):
    """Expense line on a payment request: qty x unit cost = amount."""
    __tablename__ = "payment_line_items"

    id = Column(Integer, primary_key=True, index=True)
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=False, index=True)
    description = Column(String(300), default="")
    quantity = Column(Float, default=1.0)
    unit_cost = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    sort_order = Column(Integer, default=0)


class PaymentApprovalLog(Base):
    __tablename__ = "payment_approval_logs"

    id = Column(Integer, primary_key=True, index=True)
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50))  # submit, program_approve, finance_approve, reject, pay
    comment = Column(Text, default="")
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
    budget_amount = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    contact_email = Column(String(150), default="")
    contact_phone = Column(String(50), default="")
    cac_number = Column(String(100), default="")
    experience_years = Column(Integer, default=0)  # min 3 for medical
    similar_contracts_count = Column(Integer, default=0)  # min 2
    tax_clearance = Column(String(50), default="")  # years or "valid"
    bank = Column(String(150), default="")
    reg_with_govt = Column(String(50), default="")
    audit_3yrs = Column(String(50), default="")
    logistics_footprint = Column(Text, default="")  # warehouse / delivery to Benin City
    nafdac_status = Column(String(50), default="")  # valid / pending
    pcn_license = Column(String(100), default="")  # for Lot 2 pharma
    iso_13485 = Column(Boolean, default=False)
    cgm_p = Column(Boolean, default=False)
    experience = Column(String(100), default="")  # legacy free-text
    description = Column(Text, default="")
    amount = Column(Float, default=0.0)
    score = Column(Float, default=0.0)
    is_prequalified = Column(Boolean, default=False)
    eligibility_status = Column(String(30), default="pending")  # pending | eligible | ineligible
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Soft-delete for demo data
    is_demo = Column(Boolean, default=False)


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
    status = Column(String(20), default="open")  # open | in_progress | resubmitted | resolved | dismissed
    original_debit = Column(Float, nullable=True)
    original_credit = Column(Float, nullable=True)
    corrected_debit = Column(Float, nullable=True)
    corrected_credit = Column(Float, nullable=True)
    corrected_description = Column(Text, nullable=True)
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
    statement_balance = Column(Float, default=0.0)  # closing balance as per bank statement
    book_balance = Column(Float, default=0.0)  # balance as per cashbook after ticks
    bank_charges = Column(Float, default=0.0)
    bank_charges_note = Column(Text, default="")
    unpresented_cheques = Column(Float, default=0.0)
    deposits_in_transit = Column(Float, default=0.0)
    status = Column(String(20), default="draft")  # draft | approved
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approver_stamp = Column(String(120), nullable=True)  # initials + date
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class StoredReport(Base):
    """PDF reports saved after download + sync (internal memory)."""
    __tablename__ = "stored_reports"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    report_type = Column(String(60), nullable=False)
    title = Column(String(200), default="")
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    synced = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProcurementService(Base):
    """Service / item line for procurement RFQ."""
    __tablename__ = "procurement_services"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProcurementRFQ(Base):
    """Request for quotation / LTA tender."""
    __tablename__ = "procurement_rfqs"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    rfq_no = Column(String(50), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    lot = Column(String(50), default="")  # Lot 1 FP Commodities | Lot 2 Medical Consumables
    service_id = Column(Integer, ForeignKey("procurement_services.id"), nullable=True)
    committee_id = Column(Integer, ForeignKey("procurement_committees.id"), nullable=True)
    description = Column(Text, default="")
    technical_specs = Column(Text, default="")  # JSON or text from TOR annexes
    evaluation_method = Column(String(50), default="lowest_price_technically_compliant")  # or QCBS
    status = Column(String(30), default="open")  # open | preliminary | technical_eval | financial_eval | awarded | closed
    submission_deadline = Column(DateTime, nullable=True)
    delivery_location = Column(String(200), default="Benin City, Edo State, Nigeria")
    min_shelf_life_months = Column(Integer, default=6)  # 6 for FP; 75% or 24m for consumables
    is_lta = Column(Boolean, default=True)
    lta_duration_months = Column(Integer, default=18)
    requesting_officer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_demo = Column(Boolean, default=False)


class ProcurementQuote(Base):
    """Vendor bid / quotation against an RFQ. Mandatory docs + validation before accept."""
    __tablename__ = "procurement_quotes"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("procurement_rfqs.id"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    vendor_name = Column(String(200), default="")
    amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    delivery_days = Column(Integer, default=0)
    lead_time_weeks_larc = Column(Integer, default=12)  # for Implants/IUCDs
    lead_time_weeks_other = Column(Integer, default=8)
    notes = Column(Text, default="")
    # Evaluation stages (per TOR)
    preliminary_pass = Column(Boolean, default=False)  # docs complete, signed forms
    technical_pass = Column(Boolean, default=False)  # pass/fail on specs, NAFDAC, experience
    technical_score = Column(Float, default=0.0)
    financial_rank = Column(Integer, nullable=True)  # 1 = lowest among technical pass
    system_score = Column(Float, default=0.0)  # price/docs 40%
    committee_score = Column(Float, default=0.0)  # 60%
    final_score = Column(Float, default=0.0)
    status = Column(String(30), default="draft")  # draft | submitted | preliminary | technical | financial | winner | rejected
    mandatory_docs_complete = Column(Boolean, default=False)
    shelf_life_commitment = Column(Boolean, default=False)  # written commitment ≥6 months / 75%
    manufacturer_auth = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    is_demo = Column(Boolean, default=False)


class ProcurementCommittee(Base):
    """Named evaluation committee for procurement."""
    __tablename__ = "procurement_committees"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProcurementCommitteeMember(Base):
    __tablename__ = "procurement_committee_members"
    id = Column(Integer, primary_key=True, index=True)
    committee_id = Column(Integer, ForeignKey("procurement_committees.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    member_name = Column(String(200), nullable=False)
    role_title = Column(String(100), default="Member")  # Chair, Secretary, Member
    is_active = Column(Boolean, default=True)


class QuoteMemberScore(Base):
    """Individual committee member score on a quote (part of 60%)."""
    __tablename__ = "quote_member_scores"
    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("procurement_quotes.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("procurement_committee_members.id"), nullable=False)
    score = Column(Float, default=0.0)  # 0-60 personal score
    comment = Column(Text, default="")
    scored_at = Column(DateTime, default=datetime.utcnow)


class PurchaseOrder(Base):
    """PO created after committee awards winning vendor."""
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    po_no = Column(String(50), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("procurement_rfqs.id"), nullable=True)
    quote_id = Column(Integer, ForeignKey("procurement_quotes.id"), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    vendor_name = Column(String(200), default="")
    amount = Column(Float, default=0.0)
    description = Column(Text, default="")
    status = Column(String(30), default="pending_officer")  # pending_officer | submitted_payment | paid | cancelled
    requesting_officer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=True)
    debit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    project_code_id = Column(Integer, ForeignKey("project_codes.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProcurementDocument(Base):
    """Archive / mandatory documents attached to RFQ / PO / quote / vendor / delivery."""
    __tablename__ = "procurement_documents"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("procurement_rfqs.id"), nullable=True, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True, index=True)
    quote_id = Column(Integer, ForeignKey("procurement_quotes.id"), nullable=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True, index=True)
    delivery_id = Column(Integer, nullable=True, index=True)  # FK to goods_receipts.id (defined below)
    filename = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    content_type = Column(String(100), default="application/pdf")
    size_bytes = Column(Integer, default=0)
    # Mandatory types aligned to TORs:
    # vendor: cac, tax_clearance, nafdac, maf, pcn_license, iso_cert, experience_letter, logistics_proof, sop_recall
    # bid: technical_proposal, financial_proposal, shelf_life_commitment, manufacturer_auth, batch_docs
    # delivery: packing_list, coa, expiry_docs, storage_guidance, grn
    doc_type = Column(String(80), default="support")
    is_mandatory = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GoodsReceipt(Base):
    """Delivery acceptance – all conditions (shelf-life, quality, packing, guidance doc) must be met."""
    __tablename__ = "goods_receipts"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    grn_no = Column(String(50), nullable=False, index=True)
    delivery_date = Column(Date, default=date.today)
    received_by = Column(String(150), default="")
    store_location = Column(String(200), default="Benin City central store")
    # Condition checks
    quantities_ok = Column(Boolean, default=False)
    package_integrity_ok = Column(Boolean, default=False)
    shelf_life_ok = Column(Boolean, default=False)  # ≥6 months or 75%/24m
    regulatory_docs_ok = Column(Boolean, default=False)
    storage_guidance_received = Column(Boolean, default=False)
    all_conditions_met = Column(Boolean, default=False)
    rejection_reason = Column(Text, default="")
    status = Column(String(30), default="pending")  # pending | accepted | rejected | partial
    notes = Column(Text, default="")
    accepted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_demo = Column(Boolean, default=False)


class ProcurementInvoice(Base):
    """Final invoice from vendor after accepted GRN – flows to Finance for payment request."""
    __tablename__ = "procurement_invoices"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    grn_id = Column(Integer, ForeignKey("goods_receipts.id"), nullable=True)
    invoice_no = Column(String(80), nullable=False)
    invoice_date = Column(Date, default=date.today)
    amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    status = Column(String(30), default="received")  # received | under_review | approved_for_payment | paid | disputed
    payment_request_id = Column(Integer, ForeignKey("payment_requests.id"), nullable=True)
    finance_notes = Column(Text, default="")
    submitted_to_finance_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_demo = Column(Boolean, default=False)


class Currency(Base):
    __tablename__ = "currencies"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(80), nullable=False)
    symbol = Column(String(10), default="")
    decimal_places = Column(Integer, default=2)
    is_active = Column(Boolean, default=True)
    is_base = Column(Boolean, default=False)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    id = Column(Integer, primary_key=True, index=True)
    base_code = Column(String(10), nullable=False, index=True)
    quote_code = Column(String(10), nullable=False, index=True)
    rate = Column(Float, nullable=False)
    rate_date = Column(Date, default=date.today, index=True)
    source = Column(String(40), default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)


class ErpTask(Base):
    __tablename__ = "erp_tasks"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    task_type = Column(String(40), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    status = Column(String(30), default="draft", index=True)
    priority = Column(String(20), default="normal")
    payload_json = Column(Text, default="{}")
    assigned_role = Column(String(40), default="owner")
    idempotency_key = Column(String(80), nullable=True, index=True)
    error = Column(Text, default="")
    attempts = Column(Integer, default=0)
    created_by = Column(String(50), default="system")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
