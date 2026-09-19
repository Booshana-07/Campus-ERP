"""
Phase 3B, section 7 — `users.pdf`.

Produces a user roster containing exactly four fields: Name, Role, Email,
Status.

On passwords: this module's public function accepts a plain list of
dictionaries and reads only the four keys it needs. It has no access to a
database session, no knowledge of the `password_hash` column, and no code path
that could include credential material even if a caller passed extra keys in.
The platform does not store plaintext passwords at all, so there is nothing to
redact — but the narrow interface makes the guarantee structural rather than a
matter of remembering.

reportlab is an optional dependency. If it isn't installed the admin endpoint
returns a clear 503 rather than a stack trace.
"""
import datetime
from typing import List

try:  # pragma: no cover - depends on the environment
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _REPORTLAB = True
except ImportError:  # pragma: no cover
    _REPORTLAB = False


PDF_UNAVAILABLE_MESSAGE = (
    "PDF export needs the `reportlab` package. Install it with: "
    "pip install -r requirements.txt"
)

# Fields that are allowed into the document. Anything else in the input dict is
# ignored — an explicit allow-list, so a future caller cannot widen it by accident.
ALLOWED_FIELDS = ("name", "role", "email", "status")

STATUS_COLORS = {
    "APPROVED": colors.HexColor("#198754") if _REPORTLAB else None,
    "PENDING": colors.HexColor("#fd7e14") if _REPORTLAB else None,
    "REJECTED": colors.HexColor("#dc3545") if _REPORTLAB else None,
    "SUSPENDED": colors.HexColor("#6c757d") if _REPORTLAB else None,
}


def reportlab_available() -> bool:
    return _REPORTLAB


def build_users_pdf(users: List[dict], generated_by: str = "Administrator") -> bytes:
    """
    Render the roster and return the PDF as bytes.

    `users` is a list of dicts; only `name`, `role`, `email` and `status` are read.
    """
    if not _REPORTLAB:
        raise RuntimeError(PDF_UNAVAILABLE_MESSAGE)

    # Defensive copy through the allow-list — nothing outside ALLOWED_FIELDS
    # can reach the rendered document.
    safe_rows = [
        {key: str(u.get(key, "") or "") for key in ALLOWED_FIELDS}
        for u in (users or [])
    ]

    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="SENSORA — User Accounts",
        author="SENSORA Campus Emergency Response Platform",
        subject="User roster (name, role, email, status)",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SensoraTitle", parent=styles["Title"], fontSize=18, spaceAfter=2,
        textColor=colors.HexColor("#171a2b"),
    )
    subtitle_style = ParagraphStyle(
        "SensoraSub", parent=styles["Normal"], fontSize=9.5,
        textColor=colors.HexColor("#5a6172"), alignment=TA_CENTER, spaceAfter=2,
    )
    cell_style = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=9, leading=12,
    )
    note_style = ParagraphStyle(
        "Note", parent=styles["Normal"], fontSize=8,
        textColor=colors.HexColor("#5a6172"),
    )

    story = []
    story.append(Paragraph("SENSORA — User Accounts", title_style))
    story.append(
        Paragraph(
            "AI-Powered Campus Emergency Response Platform", subtitle_style
        )
    )
    story.append(
        Paragraph(
            f"Generated {datetime.datetime.utcnow():%d %B %Y, %H:%M} UTC "
            f"&nbsp;·&nbsp; by {generated_by} &nbsp;·&nbsp; {len(safe_rows)} account(s)",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))

    # ---- summary by status ----
    counts = {}
    for row in safe_rows:
        key = (row["status"] or "UNKNOWN").upper()
        counts[key] = counts.get(key, 0) + 1
    if counts:
        summary = " &nbsp;|&nbsp; ".join(
            f"<b>{status}</b>: {count}" for status, count in sorted(counts.items())
        )
        story.append(Paragraph(summary, subtitle_style))
        story.append(Spacer(1, 10))

    # ---- table ----
    header = ["#", "Name", "Role", "Email", "Status"]
    data = [header]
    for index, row in enumerate(safe_rows, start=1):
        data.append([
            str(index),
            Paragraph(row["name"], cell_style),
            row["role"],
            Paragraph(row["email"], cell_style),
            (row["status"] or "").upper(),
        ])

    if len(data) == 1:
        data.append(["—", Paragraph("No user accounts found.", cell_style), "", "", ""])

    table = Table(
        data,
        colWidths=[10 * mm, 45 * mm, 24 * mm, 66 * mm, 29 * mm],
        repeatRows=1,
    )

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#171a2b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe3e8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f8fa")]),
    ]
    # Colour the status column so the roster is scannable.
    for row_index, row in enumerate(safe_rows, start=1):
        colour = STATUS_COLORS.get((row["status"] or "").upper())
        if colour is not None:
            style.append(("TEXTCOLOR", (4, row_index), (4, row_index), colour))
            style.append(("FONTNAME", (4, row_index), (4, row_index), "Helvetica-Bold"))

    table.setStyle(TableStyle(style))
    story.append(table)

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "This document lists account names, roles, email addresses and account "
            "statuses only. It contains no passwords, password hashes or "
            "authentication material of any kind.",
            note_style,
        )
    )

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#8a90a0"))
        canvas.drawString(18 * mm, 10 * mm, "SENSORA — Confidential. Contains no credentials.")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
