"""Plain-text and PDF exports for the post-trade risk audit report."""

from __future__ import annotations

import io
import re


def report_to_txt(report_markdown: str) -> str:
    """Convert the report structure to clean plain text."""
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
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as error:
        raise RuntimeError("PDF export requires the reportlab package.") from error

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
