"""
RepairDesk — repair-shop job-card tracker.
printing.py: printable job receipts (PDF) using reportlab.

Two formats:
  * A4 receipt  — full job card for the customer's record.
  * 80mm slip  — compact thermal-printer receipt.

generate_receipt(job, totals, shop_name, payments, paper="A4") -> file path.
The caller opens/prints the PDF; we never talk to the printer directly so
the shop can use their own print dialog on Windows.
"""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _receipts_dir() -> str:
    base = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "repairdesk_data", "receipts"
    )
    os.makedirs(base, exist_ok=True)
    return base


def _money(x: float) -> str:
    return f"Rs. {x:,.2f}"


def generate_receipt(
    job: dict,
    totals: dict,
    shop_name: str = "RepairDesk",
    payments: list | None = None,
    paper: str = "A4",
) -> str:
    """Build the receipt PDF and return its path. paper is 'A4' or '80mm'."""
    payments = payments or []
    shop_name = shop_name or "RepairDesk"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    filename = f"job-receipt-{job['job_code']}-{stamp}.pdf"
    path = os.path.join(_receipts_dir(), filename)

    if paper == "80mm":
        _draw_thermal(path, job, totals, shop_name, payments)
    else:
        _draw_a4(path, job, totals, shop_name, payments)
    return path


# ---------------------------------------------------------------------- A4
def _draw_a4(path: str, job: dict, totals: dict, shop_name: str, payments: list) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    y = h - 45

    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, y, shop_name)
    y -= 20
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, y, "Repair Job Card")
    y -= 8
    c.setLineWidth(1)
    c.line(40, y, w - 40, y)
    y -= 25

    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, f"Job ID: {job['job_code']}")
    c.setFont("Helvetica", 11)
    c.drawRightString(w - 40, y, f"Received: {job['received_at'][:10]}")
    y -= 28

    rows = [
        ("Customer", job["customer_name"]),
        ("Phone", job["phone"]),
        ("Device", job["device"]),
        ("Reported issue", job["issue"] or "-"),
        ("Accessories left", job["accessories"] or "-"),
        ("Promised by", job["promised_at"] or "-"),
        ("Status", job["status"]),
    ]
    c.setFont("Helvetica", 11)
    for label, value in rows:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(150, y, str(value))
        y -= 20

    y -= 8
    c.line(40, y, w - 40, y)
    y -= 22

    money_rows = [
        ("Estimated cost", totals["estimated"]),
        ("Advance paid", totals["advance"]),
        ("Balance due", totals["due"]),
    ]
    for label, amount in money_rows:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, f"{label}:")
        c.drawRightString(w - 40, y, _money(amount))
        y -= 20

    if payments:
        y -= 10
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Payments")
        y -= 18
        c.setFont("Helvetica", 10)
        for p in payments:
            c.drawString(40, y, f"{p['paid_at'][:10]}  {p['mode']}")
            c.drawRightString(w - 40, y, _money(float(p["amount"])))
            y -= 15

    if job["notes"]:
        y -= 10
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Notes")
        y -= 18
        c.setFont("Helvetica", 10)
        c.drawString(40, y, job["notes"][:90])

    y = 120
    c.setFont("Helvetica", 10)
    c.drawString(40, y, "Customer signature: ____________________")
    c.drawRightString(w - 40, y, "Shop stamp / signature: ____________________")
    y -= 25
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(
        w / 2, y, "Please bring this card when collecting your device. Thanks!"
    )
    c.showPage()
    c.save()


# ---------------------------------------------------------------------- 80mm thermal
def _draw_thermal(path: str, job: dict, totals: dict, shop_name: str, payments: list) -> None:
    width = 80 * mm
    # Tall enough page; unused space simply stays blank.
    height = 140 * mm
    c = canvas.Canvas(path, pagesize=(width, height))
    x = 6 * mm
    y = height - 10 * mm
    inner = width - 12 * mm

    def center(text: str, size: int = 10, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawCentredString(width / 2, y, text)
        y -= (size + 5)

    def row(label: str, value: str) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, label + ":")
        c.setFont("Helvetica", 9)
        c.drawString(x + 34 * mm, y, str(value)[:32])
        y -= 14

    def rule() -> None:
        nonlocal y
        c.setLineWidth(0.5)
        c.line(x, y, x + inner, y)
        y -= 12

    center(shop_name, 14, bold=True)
    center("Repair Job Card", 10)
    rule()
    row("Job", job["job_code"])
    row("Date", job["received_at"][:10])
    row("Name", job["customer_name"][:28])
    row("Phone", job["phone"])
    row("Device", job["device"][:28])
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Issue:")
    y -= 12
    c.setFont("Helvetica", 9)
    issue = job["issue"] or "-"
    # Wrap long issue text in 34-char chunks.
    for i in range(0, len(issue), 34):
        c.drawString(x, y, issue[i : i + 34])
        y -= 12
    rule()
    row("Estimate", _money(totals["estimated"]))
    row("Paid", _money(totals["advance"]))
    row("Due", _money(totals["due"]))
    rule()
    center("Bring this slip to collect your device.", 9)
    c.showPage()
    c.save()
