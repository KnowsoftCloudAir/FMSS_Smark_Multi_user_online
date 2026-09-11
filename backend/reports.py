"""PDF / Excel report builders with company branding."""
from io import BytesIO
from pathlib import Path
from datetime import datetime, date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import csv

STATIC = Path(__file__).parent.parent / "static" / "images"


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="TitleBrand", fontSize=16, leading=20, alignment=TA_CENTER, spaceAfter=4, textColor=colors.HexColor("#0F1C3A")))
    s.add(ParagraphStyle(name="SubBrand", fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#5A6A7A")))
    s.add(ParagraphStyle(name="ReportH", fontSize=13, leading=16, alignment=TA_CENTER, spaceBefore=8, spaceAfter=8, textColor=colors.HexColor("#1A6B9A")))
    s.add(ParagraphStyle(name="Small", fontSize=8, leading=10, textColor=colors.HexColor("#5A6A7A")))
    s.add(ParagraphStyle(name="Cell", fontSize=8, leading=10))
    return s


def company_header(story, company, report_title, currency_code="NGN", currency_symbol="₦"):
    styles = _styles()
    logo_path = None
    if company and getattr(company, "logo_path", None):
        # /static/images/xxx -> filesystem
        lp = str(company.logo_path).replace("/static/images/", "")
        cand = STATIC / lp
        if cand.exists():
            logo_path = cand
        elif (STATIC / "logo.png").exists():
            logo_path = STATIC / "logo.png"
    elif (STATIC / "logo.png").exists():
        logo_path = STATIC / "logo.png"

    if logo_path:
        try:
            img = Image(str(logo_path), width=4.5 * cm, height=1.6 * cm, kind="proportional")
            story.append(img)
        except Exception:
            pass

    name = company.name if company else "Knowsoft FMSS"
    addr = getattr(company, "address", "") or ""
    story.append(Paragraph(name, styles["TitleBrand"]))
    if addr:
        story.append(Paragraph(addr, styles["SubBrand"]))
    story.append(Paragraph(report_title, styles["ReportH"]))
    story.append(Paragraph(
        f"Reporting currency: {currency_symbol} ({currency_code}) &nbsp;&nbsp;|&nbsp;&nbsp; Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        styles["Small"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A6B9A"), spaceAfter=10))
    return styles


def table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F1C3A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C5CED8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F4FA")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])


def build_pdf(company, title, headers, rows, currency_code="NGN", currency_symbol="₦", landscape_mode=False, footer_lines=None):
    buf = BytesIO()
    pagesize = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    story = []
    styles = company_header(story, company, title, currency_code, currency_symbol)
    data = [headers] + rows
    col_w = (pagesize[0] - 24 * mm) / max(len(headers), 1)
    t = Table(data, colWidths=[col_w] * len(headers), repeatRows=1)
    t.setStyle(table_style())
    story.append(t)
    if footer_lines:
        story.append(Spacer(1, 8))
        for line in footer_lines:
            story.append(Paragraph(str(line), styles["Small"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Prepared with Knowsoft FMSS ERP — Double-entry accounting", styles["Small"]))
    doc.build(story)
    buf.seek(0)
    return buf


def build_csv(headers, rows):
    si = BytesIO()
    # write as text then encode
    from io import StringIO
    s = StringIO()
    w = csv.writer(s)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return BytesIO(s.getvalue().encode("utf-8"))


# IFRS reference map for common account types / line items
IFRS_REFS = {
    "Asset": "IAS 1 Presentation of Financial Statements; IFRS 9 / IAS 16 as applicable",
    "Liability": "IAS 1; IFRS 9 Financial Instruments",
    "Equity": "IAS 1; IAS 32 Financial Instruments: Presentation",
    "Income": "IFRS 15 Revenue from Contracts with Customers",
    "Expense": "IAS 1; IAS 2 / IAS 19 / IAS 16 as applicable",
    "Cash": "IAS 7 Statement of Cash Flows",
    "Non-current assets": "IAS 16 Property, Plant and Equipment",
    "Current assets": "IAS 1; IAS 2 Inventories; IFRS 9",
    "Current liabilities": "IAS 1; IFRS 9",
    "Non-current liabilities": "IAS 1; IFRS 9",
    "Revenue": "IFRS 15",
    "Operating expenses": "IAS 1",
    "Operating activities": "IAS 7",
    "Investing activities": "IAS 7",
    "Financing activities": "IAS 7",
}


def ifrs_for(label: str, account_type: str = "") -> str:
    for k, v in IFRS_REFS.items():
        if k.lower() in (label or "").lower():
            return v
    return IFRS_REFS.get(account_type, "IAS 1 Presentation of Financial Statements")
