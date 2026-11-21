"""Plain-text and PDF exports for the post-trade risk audit report."""

from __future__ import annotations

import io
import re


def report_to_txt(report_markdown: str) -> str:
    """Convert the report structure to clean plain text."""
    if not isinstance(report_markdown, str):
        report_markdown = "" if report_markdown is None else str(report_markdown)
    lines: list[str] = []
    for raw_line in report_markdown.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if line.startswith("#"):
            line = re.sub(r"^#+\s*", "", line)
            lines.append(line)
            lines.append("=" * len(line))
            continue
        if re.fullmatch(r"\|[-| :]+\|", line):
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            lines.append(" | ".join(cells))
            continue
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def report_to_pdf(report_markdown: str) -> bytes:
    """Render the report as a clean PDF."""
    if not isinstance(report_markdown, str):
        report_markdown = "" if report_markdown is None else str(report_markdown)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        return _fallback_pdf(report_to_txt(report_markdown))

    text = report_to_txt(report_markdown)
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="R-TATS Post-Trade & Risk Audit Report",
    )
    styles = getSampleStyleSheet()
    flowables = []
    headings = {
        "Run Parameters",
        "What Worked",
        "What Didn't",
        "High-Cost Stress Test",
        "Executed Buys & Sells",
        "Risk Check Rejections & Data Hygiene",
    }
    title_seen = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flowables.append(Spacer(1, 6))
            continue
        if set(line) == {"="}:
            continue
        escaped = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        if not title_seen:
            flowables.append(Paragraph(escaped, styles["Title"]))
            title_seen = True
        elif line in headings:
            flowables.append(Paragraph(escaped, styles["Heading2"]))
        else:
            flowables.append(Paragraph(escaped, styles["BodyText"]))
    document.build(flowables)
    return buffer.getvalue()


def _fallback_pdf(text: str) -> bytes:
    """Create a valid one-page PDF if ReportLab is unavailable."""
    lines = text.splitlines()
    escaped_lines = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines[:55]
    ]
    stream_parts = ["BT", "/F1 9 Tf", "54 738 Td", "11 TL"]
    for index, line in enumerate(escaped_lines):
        if index:
            stream_parts.append("T*")
        stream_parts.append(f"({line[:180]}) Tj")
    stream_parts.append("ET")
    stream = "\n".join(stream_parts).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(b"xref\n0 6\n")
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)
