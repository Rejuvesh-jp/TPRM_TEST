from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── Dark Theme Colors (v2 palette) ───────────────────────────────────────
DARK_BG    = RGBColor(0x0A, 0x1A, 0x2E)
PANEL_BG   = RGBColor(0x05, 0x10, 0x20)
CARD_BG    = RGBColor(0x0F, 0x2A, 0x44)
TEAL       = RGBColor(0x00, 0xD4, 0xAA)
TEAL_DIM   = RGBColor(0x00, 0x80, 0x68)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GRAY = RGBColor(0xCC, 0xDD, 0xEE)
MID_GRAY   = RGBColor(0x88, 0x99, 0xAA)
DARK_LINE  = RGBColor(0x1A, 0x3A, 0x5A)

prs = Presentation()
prs.slide_width  = Inches(13.33)
prs.slide_height = Inches(7.5)

# ── helpers ──────────────────────────────────────────────────────────────

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

def txt(slide, text, x, y, w, h, size, bold=False,
        color=WHITE, align=PP_ALIGN.LEFT, italic=False):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    p  = tf.paragraphs[0]
    p.alignment = align
    r  = p.add_run()
    r.text           = text
    r.font.size      = Pt(size)
    r.font.bold      = bold
    r.font.color.rgb = color
    r.font.italic    = italic
    return tb

def header_band(slide, label, title, subtitle):
    """Shared header style across both slides."""
    rect(slide, 0, 0, 13.33, 0.07, TEAL)
    rect(slide, 0, 0.07, 13.33, 1.05, PANEL_BG)
    rect(slide, 0.35, 0.20, 2.2, 0.34, TEAL)
    txt(slide, label, 0.35, 0.20, 2.2, 0.34,
        8.5, bold=True, color=DARK_BG, align=PP_ALIGN.CENTER)
    txt(slide, title, 2.72, 0.17, 10.3, 0.56, 20, bold=True, color=WHITE)
    txt(slide, subtitle, 2.72, 0.71, 10.3, 0.36, 10,
        color=TEAL, italic=True)
    rect(slide, 0.35, 1.16, 12.63, 0.03, DARK_LINE)

def app_heading(slide):
    """Top-right application name tag."""
    txt(slide, "TPRM AI  |  Assessment Platform",
        8.80, 0.23, 4.15, 0.32, 8.5,
        bold=True, color=TEAL, align=PP_ALIGN.RIGHT)

def footer(slide, num):
    rect(slide, 0, 6.85, 13.33, 0.65, PANEL_BG)
    rect(slide, 0, 6.85, 13.33, 0.03, TEAL)
    txt(slide, "CONFIDENTIAL  |  Titan Company Limited  |  2025",
        0, 6.95, 13.33, 0.4, 8, color=MID_GRAY, align=PP_ALIGN.CENTER)
    rect(slide, 12.52, 6.91, 0.48, 0.28, TEAL_DIM, lc=TEAL, lw=0.5)
    txt(slide, f"0{num}", 12.52, 6.91, 0.48, 0.28,
        8.5, bold=True, color=TEAL, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 1 — HOW IT HELPS  (was slide 2 in v2)
# ═══════════════════════════════════════════════════════════════════════════
s1 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s1, DARK_BG)

# ── Slide 1: big centred heading ─────────────────────────────────────────
rect(s1, 0, 0, 13.33, 0.07, TEAL)
rect(s1, 0, 0.07, 13.33, 1.35, PANEL_BG)

# Large centred application name
txt(s1, "TPRM AI  |  Assessment Platform",
    0, 0.12, 13.33, 0.80, 36, bold=True,
    color=WHITE, align=PP_ALIGN.CENTER)

# Teal subtitle line centred beneath
txt(s1, "From Weeks of Manual Work to Minutes of Smart Automation",
    0, 0.88, 13.33, 0.36, 11,
    color=TEAL, italic=True, align=PP_ALIGN.CENTER)

rect(s1, 0.35, 1.40, 12.63, 0.03, DARK_LINE)

# ── 6 feature cards — 2 col × 3 row ─────────────────────────────────────
cards = [
    ("📋", "Smart Vendor Screening",
     "Instant risk scoring before onboarding",
     "Automatically evaluates each vendor's sensitivity — data access, cloud usage, financial exposure — before any engagement begins."),
    ("🔍", "Automatic Document Review",
     "AI reads vendor documents so your team doesn't have to",
     "Upload questionnaires and evidence files. The platform reads, analyses and scores them instantly — no manual page-by-page review needed."),
    ("⚡", "Compliance Gap Detection",
     "Pinpoints exactly where risks and gaps exist",
     "Compares vendor claims against Titan's policies and contracts. Flags missing controls, policy conflicts and unsupported claims automatically."),
    ("🛠", "Actionable Remediation Plans",
     "Clear steps to fix every risk found",
     "For every gap identified, a prioritised action plan is generated with owners, deadlines and success criteria — ready to share with vendors."),
    ("📜", "Contract Protection",
     "Safeguard Titan with the right contract clauses",
     "Recommends contract clauses tailored to gaps found — covering data protection, incident response and compliance obligations."),
    ("📊", "Reports & Live Dashboard",
     "Audit-ready reports generated in one click",
     "Executive summaries and gap tables exported as PDF or Word. Live dashboard tracks all vendors and open risks at a glance."),
]

CW, CH = 6.30, 1.68
GX, GY = 0.18, 0.16
OX, OY = 0.27, 1.52

for i, (icon, title, oneliner, detail) in enumerate(cards):
    col = i % 2
    row = i // 2
    cx  = OX + col * (CW + GX)
    cy  = OY + row * (CH + GY)

    rect(s1, cx, cy, CW, CH, CARD_BG, lc=TEAL, lw=0.45)
    rect(s1, cx, cy, 0.06, CH, TEAL)
    rect(s1, cx+0.16, cy+0.17, 0.48, 0.48, TEAL_DIM, lc=TEAL, lw=0.5)
    txt(s1, icon, cx+0.16, cy+0.16, 0.48, 0.48, 14, align=PP_ALIGN.CENTER)
    txt(s1, title, cx+0.76, cy+0.12, CW-0.90, 0.38, 11.5, bold=True, color=WHITE)
    txt(s1, oneliner, cx+0.76, cy+0.47, CW-0.90, 0.28, 8.5, color=TEAL, italic=True)
    txt(s1, detail, cx+0.76, cy+0.76, CW-0.90, 0.85, 8.5, color=LIGHT_GRAY)

footer(s1, 1)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 2 — IMPACT & PLATFORM  (was slide 3 in v2, pure teal — no gold)
# ═══════════════════════════════════════════════════════════════════════════
s2 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s2, DARK_BG)

header_band(s2,
    "IMPACT & PLATFORM",
    "Built for Enterprise — Secure, Scalable & Easy to Use",
    "Designed to fit seamlessly within Titan's existing processes and compliance standards.")
app_heading(s2)

# ── LEFT: Business Impact numbers ────────────────────────────────────────
rect(s2, 0.27, 1.28, 5.95, 5.30, CARD_BG, lc=TEAL, lw=0.5)
rect(s2, 0.27, 1.28, 5.95, 0.50, TEAL_DIM)
txt(s2, "  BUSINESS IMPACT AT A GLANCE",
    0.35, 1.30, 5.80, 0.42, 11, bold=True, color=WHITE)

impacts = [
    ("80%",    "Reduction in manual assessment effort"),
    ("~10×",   "Faster vendor assessment turnaround"),
    ("100%",   "Consistent, unbiased risk scoring every time"),
    ("Zero",   "Missed gaps — AI reviews every document"),
    ("One",    "Unified platform for all vendor risk activities"),
]

iy = 1.92
for num, label in impacts:
    txt(s2, num,   0.45, iy, 1.30, 0.48, 22, bold=True, color=TEAL)
    txt(s2, label, 1.85, iy+0.08, 4.20, 0.38, 10, color=LIGHT_GRAY)
    rect(s2, 0.45, iy+0.52, 5.60, 0.015, DARK_LINE)
    iy += 0.82

# ── RIGHT: 4 platform strength cards — teal only ─────────────────────────
platform = [
    ("🔐", "Secure Access & Single Sign-On",
     "Integrates with Titan's Azure AD. Role-based access ensures the right people see the right data — with complete audit trails."),
    ("📧", "Instant Vendor Alerts",
     "Send risk findings directly to vendor contacts in one click. Fully formatted notifications — no manual emails required."),
    ("⚙️", "Admin & Pipeline Controls",
     "Manage users, upload Titan's policies as reference standards and control all platform settings from one admin panel."),
    ("📈", "Live Risk Dashboard",
     "Track active assessments, vendor risk trends and open gaps — giving leadership a clear, real-time picture of third-party exposure."),
]

PX, PY = 6.55, 1.28
PW, PH = 6.50, 1.27

for icon, title, desc in platform:
    rect(s2, PX, PY, PW, PH, CARD_BG, lc=TEAL, lw=0.45)
    rect(s2, PX, PY, 0.06, PH, TEAL)
    rect(s2, PX+0.18, PY+0.20, 0.44, 0.44, TEAL_DIM, lc=TEAL, lw=0.5)
    txt(s2, icon,  PX+0.18, PY+0.18, 0.44, 0.44, 13, align=PP_ALIGN.CENTER)
    txt(s2, title, PX+0.76, PY+0.10, PW-0.90, 0.36, 11.5, bold=True, color=WHITE)
    txt(s2, desc,  PX+0.76, PY+0.46, PW-0.90, 0.72, 8.8, color=LIGHT_GRAY)
    PY += PH + 0.08

footer(s2, 2)

# ── Save ─────────────────────────────────────────────────────────────────
out = "TPRM_AI_v5.pptx"
prs.save(out)
print(f"Saved: {out}")
