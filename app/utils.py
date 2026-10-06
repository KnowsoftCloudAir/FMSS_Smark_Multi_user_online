"""Helpers: amount in words, scannable barcode/QR, receipt PDF."""
from pathlib import Path
from io import BytesIO
from datetime import datetime
import secrets

try:
    from barcode import Code128
    from barcode.writer import ImageWriter
except ImportError:
    Code128 = None
    ImageWriter = None

try:
    import qrcode
except ImportError:
    qrcode = None

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

UPLOADS = Path(__file__).resolve().parent / "static" / "uploads"
BARCODES = Path(__file__).resolve().parent / "static" / "barcodes"
RECEIPTS = Path(__file__).resolve().parent / "static" / "receipts"
LOGOS = Path(__file__).resolve().parent / "static" / "logos"
PRODUCT_IMAGES = Path(__file__).resolve().parent / "static" / "products"
for d in (UPLOADS, BARCODES, RECEIPTS, LOGOS, PRODUCT_IMAGES):
    d.mkdir(parents=True, exist_ok=True)

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digits(n: int) -> str:
    if n < 20:
        return ONES[n]
    return TENS[n // 10] + ((" " + ONES[n % 10]) if n % 10 else "")


def amount_to_words(amount: float, currency: str = "Naira") -> str:
    try:
        n = int(round(float(amount)))
    except Exception:
        return ""
    if n == 0:
        return f"Zero {currency} Only"
    parts = []
    if n >= 1_000_000:
        parts.append(_two_digits(n // 1_000_000) + " Million")
        n %= 1_000_000
    if n >= 1_000:
        parts.append(_two_digits(n // 1_000) + " Thousand")
        n %= 1_000
    if n >= 100:
        parts.append(ONES[n // 100] + " Hundred")
        n %= 100
    if n:
        parts.append(_two_digits(n))
    return " ".join(p for p in parts if p) + f" {currency} Only"


def generate_barcode_image(sku: str, business_id: int) -> str:
    """
    Generate a camera-scannable code image.
    Primary: Code128 barcode. Also writes QR with same SKU for reliable phone scan.
    Returns path to primary image under /static/barcodes/.
    """
    BARCODES.mkdir(parents=True, exist_ok=True)
    sku = str(sku).strip()[:48] or "SKU"
    safe = "".join(c for c in sku if c.isalnum() or c in "-_")[:40] or "SKU"
    # Deterministic path so the same SKU always maps to the same file (code never "changes")
    # --- Code128 (1D barcode) ---
    code128_path = BARCODES / f"b{business_id}_{safe}.png"
    made = False
    if Code128 and ImageWriter:
        try:
            writer = ImageWriter()
            options = {
                "module_width": 0.4,
                "module_height": 18.0,
                "font_size": 10,
                "text_distance": 4.0,
                "quiet_zone": 4.0,
                "write_text": True,
                "dpi": 300,
            }
            base = str(code128_path.with_suffix(""))
            Code128(sku, writer=writer).write(base, options=options)
            png = Path(base + ".png")
            if png.exists():
                if png.resolve() != code128_path.resolve():
                    if code128_path.exists():
                        code128_path.unlink()
                    png.rename(code128_path)
                made = True
        except Exception as e:
            print("Code128 error:", e)

    # --- QR code (very reliable for phone cameras; encodes same SKU) ---
    qr_path = BARCODES / f"q{business_id}_{safe}.png"
    if qrcode:
        try:
            qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=2)
            qr.add_data(sku)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(str(qr_path))
            # Prefer QR as primary scan target if Code128 failed
        except Exception as e:
            print("QR error:", e)

    # Prefer QR for camera reliability; both encode exact SKU text
    if qr_path.exists():
        return f"/static/barcodes/{qr_path.name}"
    if made and code128_path.exists():
        return f"/static/barcodes/{code128_path.name}"

    # Pillow fallback: draw bold SKU (not ideal for scan)
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (320, 100), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([2, 2, 317, 97], outline="black", width=3)
        # simple bar pattern from hash of sku so something unique
        h = abs(hash(sku))
        x = 20
        for i in range(40):
            bit = (h >> (i % 28)) & 1
            w = 3 if bit else 6
            if bit:
                d.rectangle([x, 15, x + w, 70], fill="black")
            x += w + 1
        d.text((20, 75), sku[:30], fill="black")
        img.save(code128_path)
        return f"/static/barcodes/{code128_path.name}"
    except Exception as e:
        print("pillow fallback:", e)
        t = BARCODES / f"{safe}.txt"
        t.write_text(sku)
        return f"/static/barcodes/{t.name}"


def generate_qr_path_for_sku(sku: str, business_id: int) -> str:
    """Always produce a QR PNG for a SKU (for labels)."""
    if not qrcode:
        return generate_barcode_image(sku, business_id)
    BARCODES.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in str(sku) if c.isalnum() or c in "-_")[:40] or "SKU"
    path = BARCODES / f"qr{business_id}_{safe}_{secrets.token_hex(2)}.png"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(str(sku))
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(str(path))
    return f"/static/barcodes/{path.name}"


def build_barcodes_pdf(products: list, business_name: str) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, h - 40, f"{business_name} — Product codes")
    c.setFont("Helvetica", 9)
    c.drawString(30, h - 55, f"Printed {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC — scan with Payme camera")
    y = h - 90
    x = 30
    col = 0
    for p in products:
        if y < 130:
            c.showPage()
            y = h - 60
            col = 0
            x = 30
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, (p.name or "")[:28])
        c.setFont("Helvetica", 8)
        c.drawString(x, y - 12, f"SKU: {p.sku_code}")
        c.drawString(x, y - 24, f"N{p.selling_price:,.2f}")
        bp = p.barcode_path or ""
        if bp.startswith("/static/"):
            alt = Path(__file__).resolve().parent / "static" / "barcodes" / Path(bp).name
            if alt.exists() and alt.suffix.lower() in (".png", ".jpg", ".jpeg"):
                try:
                    c.drawImage(str(alt), x, y - 110, width=140, height=70, preserveAspectRatio=True, mask="auto")
                except Exception:
                    pass
        col += 1
        if col >= 3:
            col = 0
            x = 30
            y -= 140
        else:
            x += 180
    c.save()
    buf.seek(0)
    return buf


POS_WIDTH = 80 * mm
RECEIPT_STYLES = {
    "classic": "Classic POS",
    "bold": "Bold header",
    "minimal": "Minimal",
    "branded": "Branded block",
}


def build_receipt_pdf(business, sale, items, style: str = "classic") -> BytesIO:
    style = style if style in RECEIPT_STYLES else "classic"
    buf = BytesIO()
    height = 130 * mm + max(0, len(items) - 3) * 9 * mm
    c = canvas.Canvas(buf, pagesize=(POS_WIDTH, height))
    y = height - 8 * mm
    name = (business.name or "Payme Shop")[:28]

    if style == "branded":
        c.setFillColorRGB(0.08, 0.15, 0.28)
        c.rect(0, height - 22 * mm, POS_WIDTH, 22 * mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(POS_WIDTH / 2, height - 10 * mm, name)
        c.setFont("Helvetica", 7)
        c.drawCentredString(POS_WIDTH / 2, height - 15 * mm, (business.phone or "")[:28])
        c.setFillColorRGB(0, 0, 0)
        y = height - 28 * mm
    elif style == "bold":
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(POS_WIDTH / 2, y, name)
        y -= 6 * mm
        c.setStrokeColorRGB(0.96, 0.77, 0.26)
        c.setLineWidth(2)
        c.line(4 * mm, y, POS_WIDTH - 4 * mm, y)
        y -= 5 * mm
        c.setFont("Helvetica", 7)
        c.drawCentredString(POS_WIDTH / 2, y, f"Tel: {business.phone or '-'}")
        y -= 5 * mm
    elif style == "minimal":
        c.setFont("Helvetica", 10)
        c.drawCentredString(POS_WIDTH / 2, y, name)
        y -= 6 * mm
    else:
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(POS_WIDTH / 2, y, name)
        y -= 5 * mm
        c.setFont("Helvetica", 7)
        c.drawCentredString(POS_WIDTH / 2, y, f"Tel: {business.phone or '-'}")
        y -= 4 * mm
        if getattr(business, "email", None):
            c.drawCentredString(POS_WIDTH / 2, y, (business.email or "")[:36])
            y -= 4 * mm

    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(0.5)
    c.line(4 * mm, y, POS_WIDTH - 4 * mm, y)
    y -= 5 * mm
    c.setFont("Helvetica", 7)
    c.drawString(4 * mm, y, f"Receipt: {sale.receipt_no}")
    y -= 4 * mm
    c.drawString(4 * mm, y, f"Date: {sale.created_at.strftime('%Y-%m-%d %H:%M') if sale.created_at else ''}")
    y -= 4 * mm
    c.drawString(4 * mm, y, f"Pay: {(sale.payment_method or 'cash').upper()}")
    y -= 3 * mm
    c.line(4 * mm, y, POS_WIDTH - 4 * mm, y)
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 7)
    c.drawString(4 * mm, y, "Item")
    c.drawRightString(POS_WIDTH - 4 * mm, y, "Total")
    y -= 4 * mm
    c.setFont("Helvetica", 7)
    for it in items:
        c.drawString(4 * mm, y, (it.product_name or "")[:18])
        y -= 3.5 * mm
        c.drawString(6 * mm, y, f"{it.quantity:g} x {it.unit_price:,.2f}")
        c.drawRightString(POS_WIDTH - 4 * mm, y, f"{it.line_total:,.2f}")
        y -= 4.5 * mm
        if y < 28 * mm:
            break
    c.line(4 * mm, y, POS_WIDTH - 4 * mm, y)
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(4 * mm, y, "TOTAL")
    c.drawRightString(POS_WIDTH - 4 * mm, y, f"N{sale.total_amount:,.2f}")
    y -= 5 * mm
    c.setFont("Helvetica-Oblique", 6)
    c.drawString(4 * mm, y, (sale.amount_in_words or "")[:48])
    y -= 6 * mm
    c.setFont("Helvetica", 7)
    c.drawCentredString(POS_WIDTH / 2, y, "Thank you for your patronage!")
    y -= 4 * mm
    c.setFont("Helvetica", 6)
    c.drawCentredString(POS_WIDTH / 2, y, "Powered by Knowsoft Payme")
    c.save()
    buf.seek(0)
    return buf
