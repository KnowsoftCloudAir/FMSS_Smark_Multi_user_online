"""IFRS-style statement layouts (IAS 1 / IAS 7) — always show full structure; fill amounts when data exists."""
from io import BytesIO
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="Co", fontSize=10, alignment=TA_CENTER, spaceAfter=2, textColor=colors.HexColor("#1A6B9A"), fontName="Helvetica-Bold"))
    s.add(ParagraphStyle(name="Title", fontSize=9, alignment=TA_CENTER, spaceAfter=3, spaceBefore=4, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle(name="Sub", fontSize=7, alignment=TA_CENTER, spaceAfter=8, textColor=colors.HexColor("#555")))
    s.add(ParagraphStyle(name="Sec", fontSize=7, fontName="Helvetica-Bold", spaceBefore=4, spaceAfter=1))
    s.add(ParagraphStyle(name="Cell", fontSize=6.5, leading=8))
    s.add(ParagraphStyle(name="BoldCell", fontSize=6.5, leading=8, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle(name="Foot", fontSize=6, textColor=colors.HexColor("#666"), spaceBefore=6))
    s.add(ParagraphStyle(name="Note", fontSize=6, leading=7, textColor=colors.HexColor("#444")))
    return s


def _fmt(v):
    if v is None or abs(float(v)) < 0.0001:
        return "—"
    return f"{float(v):,.2f}"


def _header(story, co, title, subtitle, styles):
    if co and getattr(co, "logo_path", None):
        from pathlib import Path
        lp = Path(str(co.logo_path).replace("/static/", "static/"))
        # try common locations
        for cand in [lp, Path("static/images/logo.png"), Path(__file__).parent.parent / "static" / "images" / "logo.png"]:
            if cand.exists():
                try:
                    story.append(Image(str(cand), width=40*mm, height=14*mm, kind="proportional"))
                    break
                except Exception:
                    pass
    story.append(Paragraph(co.name if co else "Organisation", styles["Co"]))
    if co and getattr(co, "address", None):
        story.append(Paragraph(co.address, styles["Sub"]))
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(subtitle, styles["Sub"]))
    story.append(Paragraph("Prepared in accordance with IFRS (IAS 1 / IAS 7 as applicable)", styles["Foot"]))


def _P(text, style_name="Cell", styles=None):
    if styles is None:
        styles = _styles()
    if hasattr(text, "text"):  # already Paragraph
        return text
    return Paragraph(str(text).replace("\n", "<br/>"), styles[style_name])


def _table(rows, col_widths=None, styles=None):
    styles = styles or _styles()
    wrapped = []
    for i, row in enumerate(rows):
        new_row = []
        for j, cell in enumerate(row):
            if isinstance(cell, (int, float)):
                new_row.append(str(cell))
            elif hasattr(cell, "text"):
                new_row.append(cell)
            else:
                st = "BoldCell" if i == 0 or (isinstance(cell, str) and cell.startswith("<b>")) else "Cell"
                # Notes column smaller
                if j == 1 and i > 0:
                    st = "Note"
                new_row.append(_P(cell, st if st in styles else "Cell", styles))
        wrapped.append(new_row)
    t = Table(wrapped, colWidths=col_widths or [100*mm, 18*mm, 28*mm, 28*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C5CED8")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def build_sfp(co, year_label, prior_label, amounts: dict):
    """amounts keys match line codes e.g. ppe, cash, etc."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = _styles()
    story = []
    _header(story, co, "Statement of Financial Position", f"As at {year_label}", styles)
    a = amounts or {}
    def L(name, key, note=""):
        return [name, note or "", _fmt(a.get(key)), _fmt(a.get(key + "_prior"))]
    def S(name):
        return [Paragraph(f"<b>{name}</b>", styles["Cell"]), "", "", ""]
    def T(name, key):
        return [Paragraph(f"<b>{name}</b>", styles["Cell"]), "", _fmt(a.get(key)), _fmt(a.get(key + "_prior"))]

    rows = [["", "Notes", year_label, prior_label]]
    rows.append(S("ASSETS"))
    rows.append(S("Non-current assets"))
    for label, key, note in [
        ("Property, plant and equipment", "ppe", "IAS 16"),
        ("Investment property", "inv_prop", "IAS 40"),
        ("Intangible assets", "intangible", "IAS 38"),
        ("Investments in associates / joint ventures", "associates", "IAS 28"),
        ("Financial assets", "fin_assets", "IFRS 9"),
        ("Deferred tax assets", "dta", "IAS 12"),
        ("Other non-current assets", "other_nca", "IAS 1"),
    ]:
        rows.append(L(label, key, note))
    rows.append(T("Total non-current assets", "total_nca"))
    rows.append(S("Current assets"))
    for label, key, note in [
        ("Inventories", "inventory", "IAS 2"),
        ("Trade and other receivables", "receivables", "IFRS 9"),
        ("Current tax assets", "cta", "IAS 12"),
        ("Cash and cash equivalents", "cash", "IAS 7"),
        ("Other current assets", "other_ca", "IAS 1"),
    ]:
        rows.append(L(label, key, note))
    rows.append(T("Total current assets", "total_ca"))
    rows.append(T("Total assets", "total_assets"))
    rows.append(["", "", "", ""])
    rows.append(S("EQUITY AND LIABILITIES"))
    rows.append(S("Equity attributable to owners of the parent"))
    for label, key, note in [
        ("Share capital", "share_capital", "IAS 1"),
        ("Share premium", "share_premium", "IAS 1"),
        ("Retained earnings", "retained", "IAS 1"),
        ("Other reserves", "other_reserves", "IAS 1"),
    ]:
        rows.append(L(label, key, note))
    rows.append(T("Total equity attributable to owners", "total_equity_owners"))
    rows.append(L("Non-controlling interests", "nci", "IFRS 10"))
    rows.append(T("Total equity", "total_equity"))
    rows.append(S("Non-current liabilities"))
    for label, key, note in [
        ("Borrowings", "nc_borrowings", "IFRS 9"),
        ("Deferred tax liabilities", "dtl", "IAS 12"),
        ("Provisions", "nc_provisions", "IAS 37"),
        ("Other non-current liabilities", "other_ncl", "IAS 1"),
    ]:
        rows.append(L(label, key, note))
    rows.append(T("Total non-current liabilities", "total_ncl"))
    rows.append(S("Current liabilities"))
    for label, key, note in [
        ("Trade and other payables", "payables", "IFRS 9"),
        ("Borrowings", "c_borrowings", "IFRS 9"),
        ("Current tax liabilities", "ctl", "IAS 12"),
        ("Provisions", "c_provisions", "IAS 37"),
        ("Other current liabilities", "other_cl", "IAS 1"),
    ]:
        rows.append(L(label, key, note))
    rows.append(T("Total current liabilities", "total_cl"))
    rows.append(T("Total liabilities", "total_liab"))
    rows.append(T("Total equity and liabilities", "total_equity_liab"))
    story.append(_table(rows))
    story.append(Paragraph("Figures marked — indicate no balance in the ledger for that line in the reporting period.", styles["Foot"]))
    doc.build(story)
    buf.seek(0)
    return buf


def build_pl(co, year_label, prior_label, amounts: dict):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = _styles()
    story = []
    _header(story, co, "Statement of Profit or Loss and Other Comprehensive Income", f"For the year ended {year_label}", styles)
    a = amounts or {}
    def L(name, key, note=""):
        return [name, note, _fmt(a.get(key)), _fmt(a.get(key + "_prior"))]
    def T(name, key):
        return [Paragraph(f"<b>{name}</b>", styles["Cell"]), "", _fmt(a.get(key)), _fmt(a.get(key + "_prior"))]
    rows = [["", "Notes", year_label, prior_label],
            [Paragraph("<b>Continuing operations</b>", styles["Cell"]), "", "", ""],
            L("Revenue", "revenue", "IFRS 15"),
            L("Cost of sales", "cos", ""),
            T("Gross profit", "gross_profit"),
            L("Other income", "other_income", "IAS 1"),
            L("Distribution costs", "distribution", ""),
            L("Administrative expenses", "admin", ""),
            L("Other expenses", "other_exp", ""),
            T("Operating profit", "operating_profit"),
            L("Finance income", "fin_income", "IFRS 9"),
            L("Finance costs", "fin_costs", "IFRS 9"),
            L("Share of profit of associates", "share_associates", "IAS 28"),
            T("Profit before tax", "pbt"),
            L("Income tax expense", "tax", "IAS 12"),
            T("Profit for the year from continuing operations", "profit_cont"),
            L("Profit/(loss) from discontinued operations", "discontinued", "IFRS 5"),
            T("Profit for the year", "profit_year"),
            ["", "", "", ""],
            [Paragraph("<b>Other comprehensive income</b>", styles["Cell"]), "", "", ""],
            L("Remeasurement of defined benefit plans", "oci_db", "IAS 19"),
            L("Equity investments at FVOCI", "oci_fvoci", "IFRS 9"),
            L("Exchange differences on translation", "oci_fx", "IAS 21"),
            L("Cash flow hedges", "oci_hedge", "IFRS 9"),
            T("Other comprehensive income for the year, net of tax", "oci_total"),
            T("Total comprehensive income for the year", "tci"),
            ]
    story.append(_table(rows))
    doc.build(story)
    buf.seek(0)
    return buf


def build_equity(co, year_label, amounts: dict):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = _styles()
    story = []
    _header(story, co, "Statement of Changes in Equity", f"For the year ended {year_label}", styles)
    a = amounts or {}
    hdr = ["", "Share capital", "Share premium", "Retained earnings", "Other reserves", "Total owners", "NCI", "Total equity"]
    def row(label, prefix):
        keys = ["sc", "sp", "re", "or", "to", "nci", "te"]
        return [label] + [_fmt(a.get(f"{prefix}_{k}")) for k in keys]
    rows = [hdr,
            row(f"Balance at 1 January (opening)", "open"),
            row("Profit for the year", "profit"),
            row("Other comprehensive income", "oci"),
            row("Total comprehensive income", "tci"),
            row("Dividends", "div"),
            row("Issue of shares", "issue"),
            row(f"Balance at {year_label}", "close"),
            ]
    t = Table(rows, colWidths=[32*mm]+[22*mm]*7)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C5CED8")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    return buf


def build_cashflow(co, year_label, prior_label, amounts: dict):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = _styles()
    story = []
    _header(story, co, "Statement of Cash Flows (Indirect method)", f"For the year ended {year_label}", styles)
    a = amounts or {}
    def L(name, key, note=""):
        return [name, note, _fmt(a.get(key)), _fmt(a.get(key + "_prior"))]
    def T(name, key):
        return [Paragraph(f"<b>{name}</b>", styles["Cell"]), "", _fmt(a.get(key)), _fmt(a.get(key + "_prior"))]
    rows = [["", "Notes", year_label, prior_label],
            [Paragraph("<b>Cash flows from operating activities</b>", styles["Cell"]), "", "", ""],
            L("Profit before tax", "pbt", ""),
            L("Depreciation and amortisation", "depreciation", ""),
            L("Finance costs", "fin_costs", ""),
            L("Finance income", "fin_income", ""),
            L("(Increase)/decrease in inventories", "wc_inv", ""),
            L("(Increase)/decrease in trade receivables", "wc_ar", ""),
            L("Increase/(decrease) in trade payables", "wc_ap", ""),
            T("Cash generated from operations", "cash_ops"),
            L("Interest paid", "interest_paid", ""),
            L("Income taxes paid", "tax_paid", ""),
            T("Net cash from operating activities", "net_ops"),
            [Paragraph("<b>Cash flows from investing activities</b>", styles["Cell"]), "", "", ""],
            L("Purchase of property, plant and equipment", "ppe_buy", "IAS 16"),
            L("Proceeds from sale of PPE", "ppe_sell", ""),
            L("Purchase of investments", "inv_buy", ""),
            L("Interest received", "int_recv", ""),
            T("Net cash used in investing activities", "net_inv"),
            [Paragraph("<b>Cash flows from financing activities</b>", styles["Cell"]), "", "", ""],
            L("Proceeds from issue of shares", "shares", ""),
            L("Proceeds from borrowings", "borrow", ""),
            L("Repayment of borrowings", "repay", ""),
            L("Dividends paid", "div_paid", ""),
            T("Net cash from/(used in) financing activities", "net_fin"),
            T("Net increase/(decrease) in cash and cash equivalents", "net_change"),
            L("Cash and cash equivalents at beginning of year", "cash_open", "IAS 7"),
            T("Cash and cash equivalents at end of year", "cash_close"),
            ]
    story.append(_table(rows))
    doc.build(story)
    buf.seek(0)
    return buf


def build_bank_recon(co, account_name, statement_balance, book_balance, outstanding_cheques, deposits_in_transit, other_add, other_less, period):
    """Standard bank reconciliation: bank statement → book balance."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = _styles()
    story = []
    _header(story, co, "Bank Reconciliation Statement", f"{account_name} — {period}", styles)
    rows = [
        ["Particulars", "Amount"],
        ["Balance as per bank statement", f"{statement_balance:,.2f}"],
        ["Add: Deposits in transit / credits not yet in bank", f"{deposits_in_transit:,.2f}"],
        ["Add: Other additions", f"{other_add:,.2f}"],
        ["Less: Outstanding cheques / debits not yet in bank", f"({outstanding_cheques:,.2f})"],
        ["Less: Other deductions", f"({other_less:,.2f})"],
        ["Balance as per cash book (system ledger)", f"{book_balance:,.2f}"],
    ]
    t = Table(rows, colWidths=[120*mm, 45*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D5F5E3")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C5CED8")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Prepared under standard bank reconciliation practice: start from balance as per bank statement, "
        "adjust for timing differences, arrive at balance as per cash book (system cash account balance).",
        styles["Foot"],
    ))
    doc.build(story)
    buf.seek(0)
    return buf
