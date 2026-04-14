"""
Generate Security Audit Report PDF using ReportLab.
Run:  python generate_security_pdf.py
"""
import re
from pathlib import Path
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, KeepTogether, PageBreak,
)
from reportlab.platypus.flowables import Flowable

# ── Brand Colours ──────────────────────────────────────────────────────────
DARK_NAVY   = colors.HexColor("#1a1a2e")
MID_NAVY    = colors.HexColor("#16213e")
ACCENT_BLUE = colors.HexColor("#0f3460")
RED         = colors.HexColor("#dc3545")
ORANGE      = colors.HexColor("#e07b39")
YELLOW      = colors.HexColor("#ffc107")
GREEN       = colors.HexColor("#198754")
LIGHT_GREY  = colors.HexColor("#f8f9fa")
MID_GREY    = colors.HexColor("#e9ecef")
DARK_GREY   = colors.HexColor("#6c757d")
TEXT_BLACK  = colors.HexColor("#212529")
WHITE       = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm

# ── Styles ──────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def make_style(name, **kw):
    return ParagraphStyle(name, **kw)

S_TITLE = make_style("S_TITLE",
    fontName="Helvetica-Bold", fontSize=26, textColor=WHITE,
    leading=32, alignment=TA_CENTER, spaceAfter=6)

S_SUBTITLE = make_style("S_SUBTITLE",
    fontName="Helvetica", fontSize=12, textColor=colors.HexColor("#adb5bd"),
    leading=16, alignment=TA_CENTER)

S_H1 = make_style("S_H1",
    fontName="Helvetica-Bold", fontSize=14, textColor=WHITE,
    leading=18, spaceBefore=18, spaceAfter=6,
    backColor=DARK_NAVY, leftIndent=-MARGIN+2*mm, rightIndent=-MARGIN+2*mm,
    borderPad=(6, 10, 6, 10))

S_H2 = make_style("S_H2",
    fontName="Helvetica-Bold", fontSize=11, textColor=DARK_NAVY,
    leading=14, spaceBefore=14, spaceAfter=4,
    borderPad=(0, 0, 2, 0))

S_H3 = make_style("S_H3",
    fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT_BLUE,
    leading=13, spaceBefore=10, spaceAfter=3)

S_BODY = make_style("S_BODY",
    fontName="Helvetica", fontSize=9, textColor=TEXT_BLACK,
    leading=13, spaceAfter=4)

S_BODY_SMALL = make_style("S_BODY_SMALL",
    fontName="Helvetica", fontSize=8, textColor=TEXT_BLACK,
    leading=11, spaceAfter=3)

S_CODE = make_style("S_CODE",
    fontName="Courier", fontSize=8, textColor=TEXT_BLACK,
    leading=11, backColor=LIGHT_GREY,
    leftIndent=8, rightIndent=8, spaceAfter=4,
    borderPad=(4, 6, 4, 6))

S_BULLET = make_style("S_BULLET",
    fontName="Helvetica", fontSize=9, textColor=TEXT_BLACK,
    leading=13, spaceAfter=2,
    leftIndent=16, bulletIndent=4)

S_LABEL = make_style("S_LABEL",
    fontName="Helvetica-Bold", fontSize=8, textColor=WHITE,
    alignment=TA_CENTER)

S_TABLE_HEADER = make_style("S_TABLE_HEADER",
    fontName="Helvetica-Bold", fontSize=8.5, textColor=WHITE,
    leading=11, alignment=TA_CENTER)

S_TABLE_CELL = make_style("S_TABLE_CELL",
    fontName="Helvetica", fontSize=8, textColor=TEXT_BLACK, leading=11)

S_TABLE_CELL_BOLD = make_style("S_TABLE_CELL_BOLD",
    fontName="Helvetica-Bold", fontSize=8, textColor=TEXT_BLACK, leading=11)

S_FOOTER = make_style("S_FOOTER",
    fontName="Helvetica", fontSize=7.5, textColor=DARK_GREY,
    alignment=TA_CENTER)


# ── Severity badge colours ──────────────────────────────────────────────────
SEV_COLOUR = {
    "CRITICAL": RED,
    "HIGH":     ORANGE,
    "MEDIUM":   YELLOW,
    "LOW":      GREEN,
}
SEV_TEXT_COLOUR = {
    "CRITICAL": WHITE,
    "HIGH":     WHITE,
    "MEDIUM":   TEXT_BLACK,
    "LOW":      WHITE,
}

STATUS_COLOUR = {
    "❌": RED,
    "⚠️": ORANGE,
    "✅": GREEN,
}


class SeverityBadge(Flowable):
    """A coloured pill label for severity."""
    def __init__(self, label, width=60, height=14):
        super().__init__()
        self.label = label
        self.width = width
        self.height = height
        self.bg = SEV_COLOUR.get(label, DARK_GREY)
        self.fg = SEV_TEXT_COLOUR.get(label, WHITE)

    def draw(self):
        c = self.canv
        r = self.height / 2
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, self.height, r, fill=1, stroke=0)
        c.setFillColor(self.fg)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(self.width / 2, 3.5, self.label)


# ── Page templates ──────────────────────────────────────────────────────────
def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    # Header bar
    canvas.setFillColor(DARK_NAVY)
    canvas.rect(0, h - 22*mm, w, 22*mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(MARGIN, h - 13*mm, "TPRM AI Assessment Platform — Security Audit Report")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#adb5bd"))
    canvas.drawRightString(w - MARGIN, h - 13*mm, f"Generated: {date.today().strftime('%d %B %Y')}")
    # Footer
    canvas.setFillColor(MID_GREY)
    canvas.rect(0, 0, w, 10*mm, fill=1, stroke=0)
    canvas.setFillColor(DARK_GREY)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawCentredString(w / 2, 3.5*mm, f"Page {doc.page}  |  CONFIDENTIAL — Titan Company Limited  |  TPRM Security Audit")
    canvas.restoreState()


def _cover_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    # Full navy gradient background
    canvas.setFillColor(DARK_NAVY)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    # Accent bar at top
    canvas.setFillColor(ACCENT_BLUE)
    canvas.rect(0, h - 4*mm, w, 4*mm, fill=1, stroke=0)
    # Accent bar at bottom
    canvas.rect(0, 0, w, 4*mm, fill=1, stroke=0)
    # Decorative side stripe
    canvas.setFillColor(colors.HexColor("#0f3460"))
    canvas.rect(0, 0, 8*mm, h, fill=1, stroke=0)
    canvas.restoreState()


# ── Document builder ────────────────────────────────────────────────────────
def build_pdf(md_path: Path, out_path: Path):
    doc = BaseDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=2.8*cm,
        bottomMargin=1.6*cm,
        title="TPRM Security Audit Report",
        author="TPRM AI Platform",
    )

    content_frame = Frame(
        MARGIN, 1.6*cm,
        PAGE_W - 2*MARGIN, PAGE_H - 2.8*cm - 1.6*cm,
        id="content"
    )
    cover_frame = Frame(
        MARGIN, 0,
        PAGE_W - 2*MARGIN, PAGE_H,
        id="cover"
    )

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=_cover_page),
        PageTemplate(id="content", frames=[content_frame], onPage=_header_footer),
    ])

    story = []

    # ── Cover Page ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 6*cm))
    story.append(Paragraph("SECURITY AUDIT REPORT", S_TITLE))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("TPRM AI Assessment Platform", S_SUBTITLE))
    story.append(Spacer(1, 8*mm))

    # Divider line
    story.append(HRFlowable(width="60%", thickness=1, color=ACCENT_BLUE, hAlign="CENTER"))
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph(f"Generated: {date.today().strftime('%d %B %Y')}", S_SUBTITLE))
    story.append(Paragraph("Classification: CONFIDENTIAL", S_SUBTITLE))
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Titan Company Limited · Third-Party Risk Management", S_SUBTITLE))
    story.append(Spacer(1, 10*mm))

    # Summary badges on cover
    badge_data = [
        [
            Paragraph("8", make_style("_", fontName="Helvetica-Bold", fontSize=28, textColor=RED, alignment=TA_CENTER)),
            Paragraph("7", make_style("_", fontName="Helvetica-Bold", fontSize=28, textColor=ORANGE, alignment=TA_CENTER)),
            Paragraph("5", make_style("_", fontName="Helvetica-Bold", fontSize=28, textColor=YELLOW, alignment=TA_CENTER)),
            Paragraph("3", make_style("_", fontName="Helvetica-Bold", fontSize=28, textColor=GREEN, alignment=TA_CENTER)),
        ],
        [
            Paragraph("CRITICAL", S_LABEL),
            Paragraph("HIGH", S_LABEL),
            Paragraph("MEDIUM", S_LABEL),
            Paragraph("LOW", S_LABEL),
        ],
    ]
    cw = (PAGE_W - 2*MARGIN) / 4
    badge_table = Table(badge_data, colWidths=[cw]*4, rowHeights=[36, 22])
    badge_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#3d0010")),
        ("BACKGROUND", (1,0), (1,-1), colors.HexColor("#3d1f00")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#3d2f00")),
        ("BACKGROUND", (3,0), (3,-1), colors.HexColor("#002b18")),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROUNDEDCORNERS", [6]),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LINEAFTER", (0,0), (2,-1), 0.5, colors.HexColor("#333360")),
    ]))
    story.append(badge_table)
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("23 TOTAL FINDINGS  ·  15 SECURITY CHECK CATEGORIES", S_SUBTITLE))

    # Switch to content template
    story.append(PageBreak())
    story[-1].nextTemplate = "content"

    # ── Parse and render markdown ───────────────────────────────────────────
    md_text = md_path.read_text(encoding="utf-8")
    _render_markdown(md_text, story)

    doc.build(story)
    print(f"[OK] PDF written to: {out_path}")


# ── Markdown renderer ────────────────────────────────────────────────────────
def _render_markdown(text: str, story: list):
    lines = text.splitlines()
    i = 0
    in_code = False
    code_buf = []
    in_table = False
    table_rows = []
    table_has_header = False

    def flush_code():
        nonlocal code_buf
        if code_buf:
            joined = "\n".join(code_buf)
            story.append(Paragraph(joined.replace(" ", "&nbsp;").replace("\n", "<br/>"), S_CODE))
            code_buf = []

    def flush_table():
        nonlocal table_rows, table_has_header, in_table
        if not table_rows:
            return
        _render_table(table_rows, table_has_header, story)
        table_rows = []
        table_has_header = False
        in_table = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Code fence
        if stripped.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(stripped)
            i += 1
            continue

        # Table row
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Detect separator row: |---|---|
            if all(re.match(r"^[-:]+$", c) for c in cells):
                table_has_header = True
            else:
                table_rows.append(cells)
            i += 1
            continue
        else:
            if in_table:
                flush_table()

        # Blank line
        if not stripped:
            story.append(Spacer(1, 3*mm))
            i += 1
            continue

        # HR
        if stripped.startswith("---") and len(set(stripped)) <= 2:
            story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
            story.append(Spacer(1, 2*mm))
            i += 1
            continue

        # H1
        if stripped.startswith("# "):
            flush_table()
            text_part = _inline(stripped[2:])
            story.append(KeepTogether([
                Spacer(1, 4*mm),
                _section_header(text_part),
                Spacer(1, 2*mm),
            ]))
            i += 1
            continue

        # H2
        if stripped.startswith("## "):
            flush_table()
            text_part = _inline(stripped[3:])
            story.append(KeepTogether([
                Spacer(1, 4*mm),
                Paragraph(text_part, S_H2),
                HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE),
                Spacer(1, 1*mm),
            ]))
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            flush_table()
            text_part = _inline(stripped[4:])
            sev = None
            for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                if s in text_part.upper():
                    sev = s
                    break
            story.append(KeepTogether([
                Spacer(1, 3*mm),
                _finding_header(text_part, sev),
            ]))
            i += 1
            continue

        # H4
        if stripped.startswith("#### "):
            flush_table()
            text_part = _inline(stripped[5:])
            story.append(Paragraph(f"<b>{text_part}</b>", S_H3))
            i += 1
            continue

        # Bullet list
        if stripped.startswith("- "):
            flush_table()
            text_part = _inline(stripped[2:])
            story.append(Paragraph(f"• {text_part}", S_BULLET))
            i += 1
            continue

        # Numbered list
        if re.match(r"^\d+\.", stripped):
            flush_table()
            text_part = _inline(re.sub(r"^\d+\.\s*", "", stripped))
            num = re.match(r"^(\d+)\.", stripped).group(1)
            story.append(Paragraph(f"{num}. {text_part}", S_BULLET))
            i += 1
            continue

        # Normal paragraph
        flush_table()
        story.append(Paragraph(_inline(stripped), S_BODY))
        i += 1

    if in_code:
        flush_code()
    if in_table:
        flush_table()


def _escape_xml(text: str) -> str:
    """Escape XML special characters for ReportLab."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _inline(text: str) -> str:
    """Convert inline markdown to ReportLab XML."""
    # Emoji replacements first (before any escaping)
    text = text.replace("❌", "[CRITICAL]").replace("⚠️", "[WARNING]").replace("✅", "[OK]")

    # Extract code spans first to protect their content from escaping
    code_spans = {}
    def _stash_code(m):
        key = f"\x00CODE{len(code_spans)}\x00"
        inner = _escape_xml(m.group(1))
        code_spans[key] = f'<font name="Courier" size="8">{inner}</font>'
        return key
    text = re.sub(r"`(.*?)`", _stash_code, text)

    # Now escape the remaining XML-special chars
    text = _escape_xml(text)

    # Bold + italic ***
    text = re.sub(r"\*\*\*(.*?)\*\*\*", r"<b><i>\1</i></b>", text)
    # Bold **
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    # Italic *
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    # Links [text](url) — just show text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Restore code spans
    for key, val in code_spans.items():
        text = text.replace(key, val)

    return text


def _section_header(text: str) -> Paragraph:
    return Paragraph(text, S_H1)


def _finding_header(text: str, severity: str | None) -> Paragraph:
    colour_map = {
        "CRITICAL": "#dc3545",
        "HIGH":     "#e07b39",
        "MEDIUM":   "#ffc107",
        "LOW":      "#198754",
    }
    colour = colour_map.get(severity, "#0f3460") if severity else "#0f3460"
    styled = f'<font color="{colour}"><b>{text}</b></font>'
    return Paragraph(styled, S_H3)


def _render_table(rows: list, has_header: bool, story: list):
    if not rows:
        return

    usable_w = PAGE_W - 2 * MARGIN
    ncols = max(len(r) for r in rows)

    # Normalise row lengths
    rows = [r + [""] * (ncols - len(r)) for r in rows]

    # Auto-distribute column widths proportionally
    col_lens = [max(len(rows[ri][ci]) for ri in range(len(rows))) for ci in range(ncols)]
    total_len = sum(col_lens) or 1
    col_widths = [max(usable_w * (l / total_len), 1.5*cm) for l in col_lens]
    # Rescale to fit page
    scale = usable_w / sum(col_widths)
    col_widths = [w * scale for w in col_widths]

    def cell(text: str, bold=False) -> Paragraph:
        t = _inline(text)
        # Detect severity/status
        for s, col in [("CRITICAL", "#dc3545"), ("HIGH", "#e07b39"),
                       ("MEDIUM", "#ffc107"), ("LOW", "#198754"),
                       ("[CRITICAL]", "#dc3545"), ("[WARNING]", "#e07b39"), ("[OK]", "#198754")]:
            if s in t:
                t = t.replace(s, f'<font color="{col}"><b>{s}</b></font>')
        s = S_TABLE_CELL_BOLD if bold else S_TABLE_CELL
        return Paragraph(t, s)

    table_data = []
    for ri, row in enumerate(rows):
        is_header = has_header and ri == 0
        table_data.append([cell(c, bold=is_header) for c in row])

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1 if has_header else 0)

    ts = [
        ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#dee2e6")),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, LIGHT_GREY]),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ]
    if has_header:
        ts += [
            ("BACKGROUND",  (0,0), (-1,0), DARK_NAVY),
            ("TEXTCOLOR",   (0,0), (-1,0), WHITE),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,0), 8.5),
        ]
    tbl.setStyle(TableStyle(ts))
    story.append(tbl)
    story.append(Spacer(1, 3*mm))


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    md_file  = base / "SECURITY_AUDIT_REPORT.md"
    pdf_file = base / "SECURITY_AUDIT_REPORT.pdf"

    if not md_file.exists():
        print(f"[ERROR] Markdown source not found: {md_file}")
        raise SystemExit(1)

    build_pdf(md_file, pdf_file)
