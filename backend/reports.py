def amount_to_words(n, currency="Naira"):
    """Simple English amount in words for NGN-style amounts."""
    try:
        n = float(n)
    except Exception:
        return ""
    units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
             "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def under_1000(x):
        x = int(x)
        if x < 20:
            return units[x]
        if x < 100:
            return tens[x // 10] + ((" " + units[x % 10]) if x % 10 else "")
        return units[x // 100] + " Hundred" + ((" and " + under_1000(x % 100)) if x % 100 else "")

    whole = int(abs(n))
    kobo = int(round((abs(n) - whole) * 100))
    if whole == 0:
        words = "Zero"
    else:
        parts = []
        billions = whole // 1_000_000_000
        millions = (whole // 1_000_000) % 1000
        thousands = (whole // 1000) % 1000
        rem = whole % 1000
        if billions:
            parts.append(under_1000(billions) + " Billion")
        if millions:
            parts.append(under_1000(millions) + " Million")
        if thousands:
            parts.append(under_1000(thousands) + " Thousand")
        if rem:
            parts.append(under_1000(rem))
        words = " ".join(parts)
    result = f"{words} {currency}"
    if kobo:
        result += f" and {kobo}/100"
    result += " Only"
    return result


"""PDF / Excel report builders with company branding, dashboard page 1, stamps."""
from io import BytesIO
from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfgen import canvas as pdfcanvas


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="ReportH", fontSize=13, leading=16, alignment=TA_CENTER,
                         spaceBefore=6, spaceAfter=6, textColor=colors.HexColor("#1A6B9A")))
    s.add(ParagraphStyle(name="CoName", fontSize=16, leading=20, alignment=TA_CENTER,
                         spaceAfter=4, textColor=colors.HexColor("#0D3B66"), fontName="Helvetica-Bold"))
    s.add(ParagraphStyle(name="Small", fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#555555")))
    s.add(ParagraphStyle(name="BodyL", fontSize=10, leading=13, alignment=TA_LEFT))
    s.add(ParagraphStyle(name="Stamp", fontSize=11, leading=14, alignment=TA_CENTER,
                         textColor=colors.HexColor("#1A6B9A"), fontName="Helvetica-Bold"))
    return s


def _logo_path(company):
    for p in (
        Path("static/images/logo.png"),
        Path("static/images/company_logo.png"),
        Path("../static/images/logo.png"),
        Path(__file__).resolve().parent.parent / "static/images/logo.png",
    ):
        if p.exists():
            return str(p)
    return None


def company_header(story, company, report_title, currency_code="NGN", currency_symbol="₦", description=None):
    styles = _styles()
    logo = _logo_path(company)
    if logo:
        try:
            story.append(Image(logo, width=2.2*cm, height=2.2*cm))
        except Exception:
            pass
    name = getattr(company, "name", None) or "Organisation"
    story.append(Paragraph(name, styles["CoName"]))
    story.append(Paragraph(report_title, styles["ReportH"]))
    if description:
        story.append(Paragraph(description, styles["Small"]))
    story.append(Paragraph(
        f"Reporting currency: {currency_symbol} ({currency_code}) &nbsp;|&nbsp; "
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        styles["Small"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A6B9A"), spaceAfter=8))
    return styles


def dashboard_snapshot_block(story, styles, kpis: dict):
    """Page-1 dashboard summary (proxy for on-screen dashboard snapshot)."""
    story.append(Paragraph("Dashboard snapshot", styles["ReportH"]))
    if not kpis:
        story.append(Paragraph("No dashboard metrics available for this period.", styles["Small"]))
        story.append(Spacer(1, 6))
        return
    data = [["Metric", "Value"]]
    for k, v in kpis.items():
        data.append([str(k), str(v)])
    t = Table(data, colWidths=[10*cm, 6*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A6B9A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F9FC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))


def signature_block(story, styles, lines=None):
    lines = lines or ["Prepared by", "Reviewed by", "Approved by"]
    data = [[Paragraph(f"<b>{L}</b><br/><br/>_______________________<br/>Name / Date", styles["BodyL"]) for L in lines]]
    t = Table(data, colWidths=[5.5*cm] * len(lines))
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4)]))
    story.append(Spacer(1, 16))
    story.append(t)


def stamp_block(story, styles, stamp_text: str):
    if not stamp_text:
        return
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"APPROVAL STAMP: {stamp_text}", styles["Stamp"]))
    story.append(Paragraph("(Initials and date applied on approval)", styles["Small"]))


def build_pdf(company, title, headers, rows, currency_code="NGN", currency_symbol="₦",
              landscape_mode=False, footer_lines=None, description=None, kpis=None,
              stamp_text=None, signature_lines=None):
    buf = BytesIO()
    pagesize = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=12*mm, bottomMargin=14*mm)
    story = []
    styles = company_header(story, company, title, currency_code, currency_symbol, description)
    dashboard_snapshot_block(story, styles, kpis or {})
    story.append(PageBreak())

    # data table
    col_count = max(len(headers), 1)
    usable = (pagesize[0] - 24*mm)
    col_w = [usable / col_count] * col_count
    data = [headers] + (rows or [["No data"]])
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A6B9A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FBFE")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    if footer_lines:
        story.append(Spacer(1, 10))
        for fl in footer_lines:
            story.append(Paragraph(fl, styles["BodyL"]))
    stamp_block(story, styles, stamp_text)
    signature_block(story, styles, signature_lines)
    doc.build(story)
    buf.seek(0)
    return buf


def build_bank_recon_pdf(company, statement_balance, book_balance, bank_charges, bank_charges_note,
                         unpresented, deposits, ticked_rows, unticked_rows,
                         currency_code="NGN", currency_symbol="₦",
                         period_label="", stamp_text=None, kpis=None):
    """
    Formal bank reconciliation:
      Balance as per bank statement (closing)
      - Unpresented items / + deposits in transit / bank charges
      = Balance as per cashbook (after verified ticks)
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm,
                            topMargin=12*mm, bottomMargin=14*mm)
    story = []
    styles = company_header(
        story, company, "BANK RECONCILIATION STATEMENT",
        currency_code, currency_symbol,
        description=period_label or "Reconciliation of bank statement to cash book",
    )
    dashboard_snapshot_block(story, styles, kpis or {
        "Statement balance": f"{currency_symbol}{statement_balance:,.2f}",
        "Cashbook balance": f"{currency_symbol}{book_balance:,.2f}",
        "Bank charges": f"{currency_symbol}{bank_charges:,.2f}",
        "Items verified (ticked)": str(len(ticked_rows or [])),
        "Items outstanding": str(len(unticked_rows or [])),
    })
    story.append(PageBreak())

    story.append(Paragraph("<b>Reconciliation summary</b>", styles["BodyL"]))
    story.append(Spacer(1, 6))
    sum_data = [
        ["Particulars", f"Amount ({currency_symbol})"],
        ["Balance as per closing bank statement", f"{statement_balance:,.2f}"],
        ["Add: Deposits in transit / credits not on statement", f"{deposits:,.2f}"],
        ["Less: Unpresented cheques / debits not on statement", f"({unpresented:,.2f})"],
        ["Less: Bank charges (recorded on recon)", f"({bank_charges:,.2f})"],
        ["Balance as per cashbook (after verified items)", f"{book_balance:,.2f}"],
    ]
    st = Table(sum_data, colWidths=[12*cm, 5*cm])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A6B9A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F4FC")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(st)
    if bank_charges_note:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Bank charges note:</b> {bank_charges_note}", styles["BodyL"]))

    def _lines_table(title, rows):
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>{title}</b>", styles["BodyL"]))
        data = [["Date", "Entry", "Description", f"Debit ({currency_symbol})", f"Credit ({currency_symbol})"]]
        for r in (rows or []):
            data.append([
                r.get("date", ""), r.get("entry_no", ""), (r.get("description") or "")[:40],
                f"{float(r.get('debit') or 0):,.2f}", f"{float(r.get('credit') or 0):,.2f}",
            ])
        if len(data) == 1:
            data.append(["—", "—", "None", "0.00", "0.00"])
        t = Table(data, colWidths=[2.5*cm, 2.5*cm, 7*cm, 2.5*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D3B66")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ]))
        story.append(t)

    _lines_table("Items verified on bank statement (ticked)", ticked_rows)
    _lines_table("Outstanding items (not yet verified)", unticked_rows)

    stamp_block(story, styles, stamp_text)
    signature_block(story, styles, ["Prepared by (Finance)", "Reviewed / Approved by"])
    doc.build(story)
    buf.seek(0)
    return buf


def build_payment_voucher_pdf(company, pr, approvers, currency_code="NGN", currency_symbol="₦", kpis=None):
    """Beautiful payment voucher with logo, company name, payment details, signatures."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm,
                            topMargin=12*mm, bottomMargin=14*mm)
    story = []
    styles = company_header(
        story, company, "PAYMENT VOUCHER",
        currency_code, currency_symbol,
        description="Official payment document",
    )
    dashboard_snapshot_block(story, styles, kpis or {})
    story.append(PageBreak())

    words = getattr(pr, "amount_in_words", None) or amount_to_words(getattr(pr, "amount", 0) or 0)
    story.append(Paragraph(f"<b>VOUCHER No:</b> {getattr(pr, 'request_no', '')}", styles["BodyL"]))
    story.append(Spacer(1, 6))
    details = [
        ["Field", "Detail"],
        ["Payee", getattr(pr, "payee_name", "") or "—"],
        ["Amount", f"{currency_symbol}{float(getattr(pr, 'amount', 0) or 0):,.2f}"],
        ["Amount in words", words],
        ["Narration / Invoice details", (getattr(pr, "narration", None) or "")[:300]],
        ["Status", getattr(pr, "status", "")],
        ["Request date", str(getattr(pr, "created_at", "") or "")[:19]],
        ["Paid date", str(getattr(pr, "paid_at", "") or "—")[:19]],
    ]
    for label, val in (approvers or {}).items():
        details.append([label, str(val)])
    t = Table(details, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D3B66")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#E8F4FC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>Authorisation</b>", styles["BodyL"]))
    signature_block(story, styles, ["Prepared by", "Finance Officer", "Authorised signatory"])
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<i>This voucher is system-generated. Verify payee and amount before disbursement.</i>",
        styles["Small"],
    ))
    doc.build(story)
    buf.seek(0)
    return buf



def build_csv(headers, rows):
    import csv
    buf = BytesIO()
    # text wrapper
    from io import StringIO
    s = StringIO()
    w = csv.writer(s)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    buf.write(s.getvalue().encode("utf-8-sig"))
    buf.seek(0)
    return buf
