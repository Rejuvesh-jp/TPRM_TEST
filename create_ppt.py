from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# Brand Colors
DARK_BG    = RGBColor(0x0A, 0x1A, 0x2E)
PANEL_BG   = RGBColor(0x05, 0x10, 0x20)
CARD_BG    = RGBColor(0x0F, 0x2A, 0x44)
TEAL       = RGBColor(0x00, 0xD4, 0xAA)
TEAL_DIM   = RGBColor(0x00, 0x80, 0x68)
GOLD       = RGBColor(0xF5, 0xC5, 0x18)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GRAY = RGBColor(0xCC, 0xDD, 0xEE)
MID_GRAY   = RGBColor(0x88, 0x99, 0xAA)
DARK_LINE  = RGBColor(0x1A, 0x3A, 0x5A)

prs = Presentation()
prs.slide_width  = Inches(13.33)
prs.slide_height = Inches(7.5)

# ── helpers ─────────────────────────────────────────────────────────────────

def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = color

def rect(slide, x, y, w, h, fill, lc=None, lw=0.5):
    s = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if lc:
        s.line.color.rgb = lc
        s.line.width = Pt(lw)
    else:
        s.line.fill.background()
    return s

def txt(slide, text, x, y, w, h, size, bold=False, color=WHITE,
        align=PP_ALIGN.LEFT, italic=False):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    p  = tf.paragraphs[0]
    p.alignment = align
    r  = p.add_run()
    r.text        = text
    r.font.size   = Pt(size)
    r.font.bold   = bold
    r.font.color.rgb = color
    r.font.italic = italic
    return tb

def footer(slide, num):
    rect(slide, 0, 6.85, 13.33, 0.65, PANEL_BG)
    rect(slide, 0, 6.85, 13.33, 0.03, TEAL)
    txt(slide, "CONFIDENTIAL  |  Titan Company Limited  |  2025",
        0, 6.95, 13.33, 0.4, 8, color=MID_GRAY, align=PP_ALIGN.CENTER)
    txt(slide, f"0{num}", 12.6, 6.88, 0.5, 0.35, 10, bold=True, color=TEAL)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ═══════════════════════════════════════════════════════════════════════════
s1 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s1, DARK_BG)

# ── LEFT dark panel
rect(s1, 0, 0, 6.0, 7.5, PANEL_BG)

# ── Teal top bar (left panel only)
rect(s1, 0, 0, 6.0, 0.12, TEAL)

# ── Vertical teal stripe separating panels
rect(s1, 5.92, 0, 0.08, 7.5, TEAL)

# ── Subtle dot grid on left panel
for gx in [0.6, 1.8, 3.0, 4.2, 5.4]:
    for gy in [1.0, 2.0, 3.0, 4.0, 5.0, 6.5]:
        rect(s1, gx, gy, 0.035, 0.035, TEAL)

# ── Company badge
txt(s1, "TITAN COMPANY LIMITED", 0.35, 0.25, 5.3, 0.35,
    8, bold=True, color=TEAL, italic=True)
rect(s1, 0.35, 0.58, 1.4, 0.03, GOLD)

# ── Main title
txt(s1, "TPRM AI", 0.35, 0.72, 5.3, 1.05, 58, bold=True, color=WHITE)
txt(s1, "Assessment Platform", 0.35, 1.75, 5.3, 0.6,
    22, bold=False, color=TEAL)

# ── Tagline
txt(s1,
    "Assess vendor risks in minutes, not weeks.\n"
    "Automatically identify gaps, generate action plans\n"
    "and produce audit-ready reports — all in one place.",
    0.35, 2.55, 5.3, 1.1, 10.5, color=LIGHT_GRAY)

# ── Divider
rect(s1, 0.35, 3.72, 5.25, 0.03, TEAL)

# ── Impact stat pills (business-friendly)
stats = [
    ("80%", "Less Manual\nEffort"),
    ("Minutes", "vs Weeks\nTo Assess"),
    ("Auto", "Reports &\nAction Plans"),
]
sx = 0.35
for top, bot in stats:
    rect(s1, sx, 3.88, 1.68, 0.85, TEAL_DIM, lc=TEAL, lw=0.6)
    txt(s1, top,  sx+0.08, 3.90, 1.54, 0.40, 16, bold=True,
        color=TEAL, align=PP_ALIGN.CENTER)
    txt(s1, bot,  sx+0.08, 4.28, 1.54, 0.40, 7.5,
        color=LIGHT_GRAY, align=PP_ALIGN.CENTER)
    sx += 1.78

# ── "A Titan Initiative" bottom label
rect(s1, 0.35, 5.10, 2.8, 0.32, RGBColor(0x00,0x50,0x45), lc=TEAL, lw=0.5)
txt(s1, "  A TITAN COMPANY INITIATIVE", 0.35, 5.10, 2.8, 0.32,
    8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ── RIGHT — app screenshot, neatly fitted with subtle frame
# Frame / shadow effect
rect(s1, 6.22, 0.62, 6.82, 5.52, RGBColor(0x00,0xD4,0xAA))   # teal border
rect(s1, 6.28, 0.68, 6.70, 5.40, DARK_BG)                     # inner bg

try:
    s1.shapes.add_picture(
        "inputs/image.png",
        Inches(6.28), Inches(0.68),
        Inches(6.70), Inches(5.40)
    )
except Exception as e:
    txt(s1, "[App Screenshot]", 6.28, 2.5, 6.7, 1.0, 14,
        color=MID_GRAY, align=PP_ALIGN.CENTER)

# Subtle caption under image
txt(s1, "TPRM AI Platform  —  Live Dashboard View",
    6.28, 6.14, 6.70, 0.32, 8, color=MID_GRAY,
    italic=True, align=PP_ALIGN.CENTER)

footer(s1, 1)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 2 — WHAT IT DOES (Business Overview)
# ═══════════════════════════════════════════════════════════════════════════
s2 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s2, DARK_BG)
rect(s2, 0, 0, 13.33, 0.07, TEAL)
rect(s2, 0, 0.07, 13.33, 1.05, PANEL_BG)

# Label pill
rect(s2, 0.35, 0.20, 2.2, 0.34, TEAL)
txt(s2, "HOW IT HELPS", 0.35, 0.20, 2.2, 0.34,
    8.5, bold=True, color=DARK_BG, align=PP_ALIGN.CENTER)

txt(s2, "From Weeks of Manual Work to Minutes of Smart Automation",
    2.72, 0.17, 10.3, 0.56, 20, bold=True, color=WHITE)
txt(s2, "TPRM AI removes the bottlenecks of manual vendor assessments — giving your team more time to act, not analyse.",
    2.72, 0.71, 10.3, 0.36, 10, color=TEAL, italic=True)
rect(s2, 0.35, 1.16, 12.63, 0.03, DARK_LINE)

# ── 2-column layout: 3 cards left, 3 cards right ──────────────────────────
cards = [
    # (icon, title, one-liner, detail)
    ("📋", "Smart Vendor Screening",
     "Instant risk scoring before onboarding",
     "Automatically evaluates each vendor's sensitivity level — data access, cloud usage, financial exposure — before any engagement begins."),

    ("🔍", "Automatic Document Review",
     "AI reads vendor documents so your team doesn't have to",
     "Uploads vendor questionnaires and evidence files. The platform reads, analyses and scores them instantly — no manual page-by-page review needed."),

    ("⚡", "Compliance Gap Detection",
     "Pinpoints exactly where risks and gaps exist",
     "Compares vendor claims against Titan's policies and contract standards. Flags missing controls, policy conflicts and unsupported claims automatically."),

    ("🛠", "Actionable Remediation Plans",
     "Clear steps to fix every risk found",
     "For every gap identified, the platform generates a prioritised action plan with owners, deadlines and success criteria — ready to share with vendors."),

    ("📜", "Contract Protection Recommendations",
     "Safeguard Titan with the right contract clauses",
     "Recommends contract clauses tailored to the gaps found — covering data protection, incident response and compliance obligations."),

    ("📊", "Reports & Live Dashboard",
     "Audit-ready reports generated in one click",
     "Executive summaries, gap tables and remediation plans exported as PDF or Word. Live dashboard tracks all vendors, trends and open risks at a glance."),
]

col_w  = 6.30
row_h  = 1.72
gap_x  = 0.18
gap_y  = 0.18
start_x = 0.27
start_y = 1.28

for i, (icon, title, oneliner, detail) in enumerate(cards):
    col = i % 2
    row = i // 2
    cx = start_x + col * (col_w + gap_x)
    cy = start_y + row * (row_h + gap_y)

    rect(s2, cx, cy, col_w, row_h, CARD_BG, lc=TEAL, lw=0.45)

    # Left teal accent bar
    rect(s2, cx, cy, 0.06, row_h, TEAL)

    # Icon circle
    rect(s2, cx+0.16, cy+0.17, 0.48, 0.48, TEAL_DIM, lc=TEAL, lw=0.5)
    txt(s2, icon, cx+0.16, cy+0.16, 0.48, 0.48, 14,
        align=PP_ALIGN.CENTER)

    # Title
    txt(s2, title, cx+0.76, cy+0.12, col_w-0.90, 0.38,
        11.5, bold=True, color=WHITE)

    # One-liner in teal
    txt(s2, oneliner, cx+0.76, cy+0.47, col_w-0.90, 0.28,
        8.5, color=TEAL, italic=True)

    # Detail
    txt(s2, detail, cx+0.76, cy+0.76, col_w-0.90, 0.85,
        8.5, color=LIGHT_GRAY)

footer(s2, 2)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 3 — IMPACT & PLATFORM STRENGTHS
# ═══════════════════════════════════════════════════════════════════════════
s3 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s3, DARK_BG)
rect(s3, 0, 0, 13.33, 0.07, GOLD)
rect(s3, 0, 0.07, 13.33, 1.05, PANEL_BG)

# Label pill
rect(s3, 0.35, 0.20, 2.5, 0.34, GOLD)
txt(s3, "IMPACT & PLATFORM", 0.35, 0.20, 2.5, 0.34,
    8.5, bold=True, color=DARK_BG, align=PP_ALIGN.CENTER)

txt(s3, "Built for Enterprise — Secure, Scalable & Easy to Use",
    3.05, 0.17, 9.93, 0.56, 20, bold=True, color=WHITE)
txt(s3, "Designed to fit seamlessly within Titan's existing processes and compliance standards.",
    3.05, 0.71, 9.93, 0.36, 10, color=GOLD, italic=True)
rect(s3, 0.35, 1.16, 12.63, 0.03, DARK_LINE)

# ── LEFT: Business Impact Numbers ─────────────────────────────────────────
rect(s3, 0.27, 1.28, 5.95, 5.30, CARD_BG, lc=TEAL, lw=0.5)
rect(s3, 0.27, 1.28, 5.95, 0.50, TEAL_DIM)
txt(s3, "  BUSINESS IMPACT AT A GLANCE",
    0.35, 1.30, 5.80, 0.42, 11, bold=True, color=WHITE)

impacts = [
    ("80%",  "Reduction in manual assessment effort"),
    ("~10×", "Faster vendor assessment turnaround"),
    ("100%", "Consistent, unbiased risk scoring every time"),
    ("Zero", "Missed gaps — AI reviews every document line"),
    ("One",  "Unified platform for all vendor risk activities"),
]

iy = 1.92
for num, label in impacts:
    # Teal number
    txt(s3, num, 0.45, iy, 1.30, 0.48, 22, bold=True, color=TEAL)
    # Label
    txt(s3, label, 1.85, iy+0.08, 4.20, 0.38, 10, color=LIGHT_GRAY)
    rect(s3, 0.45, iy+0.52, 5.60, 0.015, DARK_LINE)
    iy += 0.82

# ── RIGHT: Platform Strengths ─────────────────────────────────────────────
platform = [
    ("🔐", "Secure Access & SSO",
     "Single Sign-On with Titan's Azure AD. Role-based access ensures the right people see the right data — with full audit trails."),
    ("📧", "Instant Vendor Alerts",
     "Send risk findings directly to vendor contacts in one click. No manual emails — the platform handles formatted notifications automatically."),
    ("⚙️", "Admin Controls",
     "Manage users, upload Titan's internal policies and contracts as reference standards, and control platform settings — all from one admin panel."),
    ("📈", "Live Risk Dashboard",
     "Track all active assessments, vendor risk trends, open gaps and monthly progress — giving leadership a clear, real-time picture of third-party risk."),
]

px = 6.55
py = 1.28
pw = 6.50
ph = 1.27

for icon, title, desc in platform:
    rect(s3, px, py, pw, ph, CARD_BG, lc=GOLD, lw=0.45)
    rect(s3, px, py, 0.06, ph, GOLD)

    # Icon
    rect(s3, px+0.18, py+0.20, 0.44, 0.44, RGBColor(0x3A,0x2A,0x00), lc=GOLD, lw=0.5)
    txt(s3, icon, px+0.18, py+0.18, 0.44, 0.44, 13, align=PP_ALIGN.CENTER)

    # Title
    txt(s3, title, px+0.76, py+0.10, pw-0.90, 0.36, 11.5, bold=True, color=GOLD)

    # Desc
    txt(s3, desc, px+0.76, py+0.46, pw-0.90, 0.72, 8.8, color=LIGHT_GRAY)

    py += ph + 0.08

footer(s3, 3)

# ── Save ──────────────────────────────────────────────────────────────────
out = "TPRM_AI_Platform_Presentation.pptx"
prs.save(out)
print(f"Saved: {out}")
