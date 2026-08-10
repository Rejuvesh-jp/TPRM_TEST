from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── Light Theme Colors ────────────────────────────────────────────────────
WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
OFF_WHITE   = RGBColor(0xF4, 0xF7, 0xFB)   # slide background
LIGHT_PANEL = RGBColor(0xE8, 0xF0, 0xF8)   # subtle panel bg
CARD_BG     = RGBColor(0xFF, 0xFF, 0xFF)   # card white
TEAL        = RGBColor(0x00, 0xB4, 0x8A)   # primary teal
TEAL_LIGHT  = RGBColor(0xD0, 0xF5, 0xEC)   # teal tint fill
TEAL_MID    = RGBColor(0x00, 0x8A, 0x6A)   # darker teal
NAVY        = RGBColor(0x0A, 0x1A, 0x3A)   # headings
DARK_TEXT   = RGBColor(0x1E, 0x2D, 0x40)   # body text
MID_TEXT    = RGBColor(0x55, 0x6B, 0x82)   # secondary text
BORDER      = RGBColor(0xC8, 0xD8, 0xE8)   # card borders
GOLD        = RGBColor(0xD4, 0x8A, 0x00)   # gold accent
GOLD_LIGHT  = RGBColor(0xFF, 0xF3, 0xD0)   # gold tint
SEPARATOR   = RGBColor(0xD0, 0xDE, 0xEC)   # thin rule

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
        color=DARK_TEXT, align=PP_ALIGN.LEFT, italic=False):
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

def footer(slide, num):
    rect(slide, 0, 6.88, 13.33, 0.62, LIGHT_PANEL)
    rect(slide, 0, 6.88, 13.33, 0.03, TEAL)
    txt(slide, "CONFIDENTIAL  |  Titan Company Limited  |  2025",
        0, 6.97, 13.33, 0.38, 8, color=MID_TEXT, align=PP_ALIGN.CENTER)
    txt(slide, f"0{num}", 12.6, 6.90, 0.5, 0.32, 10,
        bold=True, color=TEAL)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ═══════════════════════════════════════════════════════════════════════════
s1 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s1, OFF_WHITE)

# ── TOP header bar (full width teal)
rect(s1, 0, 0, 13.33, 1.10, TEAL)

# ── Teal top-bar text
txt(s1, "TITAN COMPANY LIMITED", 0.38, 0.10, 5.0, 0.32,
    8, bold=True, color=WHITE, italic=True)
txt(s1, "A TITAN INITIATIVE", 0.38, 0.40, 5.0, 0.32,
    7.5, color=RGBColor(0xCC, 0xFF, 0xEE))
txt(s1, "TPRM AI  |  Assessment Platform", 7.0, 0.22, 5.9, 0.50,
    13, bold=True, color=WHITE, align=PP_ALIGN.RIGHT)

# ── Gold accent strip below header
rect(s1, 0, 1.10, 13.33, 0.06, GOLD)

# ── LEFT content area
rect(s1, 0, 1.16, 6.0, 5.72, WHITE)   # white left panel

# Subtle dot grid
for gx in [0.5, 1.2, 1.9, 2.6, 3.3, 4.0, 4.7, 5.4]:
    for gy in [1.5, 2.2, 2.9, 3.6, 4.3, 5.0, 5.7]:
        rect(s1, gx, gy, 0.03, 0.03, TEAL_LIGHT)

# Main headline
txt(s1, "Smarter Vendor Risk.", 0.40, 1.38, 5.5, 0.80,
    38, bold=True, color=NAVY)
txt(s1, "Powered by AI.", 0.40, 2.12, 5.5, 0.65,
    38, bold=True, color=TEAL)

# Divider under headline
rect(s1, 0.40, 2.80, 4.60, 0.05, TEAL)

# Tagline
txt(s1,
    "TPRM AI automates every step of vendor risk assessment —\n"
    "from document review to gap detection to audit-ready reports.\n"
    "What once took weeks now takes minutes.",
    0.40, 2.98, 5.4, 1.05, 10.5, color=MID_TEXT)

# Impact stat pills — horizontal row
stats = [
    ("80%",      "Less Manual Effort"),
    ("Minutes",  "Not Weeks"),
    ("Auto",     "Reports & Plans"),
]
sx = 0.40
for top, bot in stats:
    rect(s1, sx, 4.22, 1.72, 0.82, TEAL_LIGHT, lc=TEAL, lw=0.7)
    txt(s1, top, sx+0.08, 4.24, 1.56, 0.38,
        17, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    txt(s1, bot, sx+0.08, 4.60, 1.56, 0.34,
        8, color=MID_TEXT, align=PP_ALIGN.CENTER)
    sx += 1.82

# Titan initiative badge
rect(s1, 0.40, 5.30, 2.60, 0.34, TEAL, lc=TEAL)
txt(s1, "  A TITAN COMPANY INITIATIVE", 0.40, 5.30, 2.60, 0.34,
    8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ── RIGHT — screenshot panel
rect(s1, 6.0, 1.16, 7.33, 5.72, LIGHT_PANEL)

# Decorative teal left-edge stripe on image panel
rect(s1, 6.0, 1.16, 0.06, 5.72, TEAL)

# Image neatly fitted with drop shadow illusion
rect(s1, 6.34, 1.46, 6.72, 4.76, BORDER)          # shadow
rect(s1, 6.28, 1.40, 6.72, 4.76, WHITE)            # white frame

try:
    s1.shapes.add_picture(
        "inputs/image.png",
        Inches(6.28), Inches(1.40),
        Inches(6.72), Inches(4.76)
    )
except Exception:
    txt(s1, "[App Screenshot]", 6.28, 3.3, 6.72, 0.6,
        13, color=MID_TEXT, align=PP_ALIGN.CENTER)

txt(s1, "TPRM AI Platform  —  Live Dashboard View",
    6.28, 6.24, 6.72, 0.30, 8,
    color=MID_TEXT, italic=True, align=PP_ALIGN.CENTER)

footer(s1, 1)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 2 — HOW IT HELPS
# ═══════════════════════════════════════════════════════════════════════════
s2 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s2, OFF_WHITE)

# Top bar
rect(s2, 0, 0, 13.33, 0.80, TEAL)
rect(s2, 0, 0.80, 13.33, 0.05, GOLD)

# Label pill on bar
rect(s2, 0.35, 0.15, 2.0, 0.34, WHITE)
txt(s2, "HOW IT HELPS", 0.35, 0.15, 2.0, 0.34,
    8.5, bold=True, color=TEAL, align=PP_ALIGN.CENTER)

txt(s2, "From Weeks of Manual Work to Minutes of Smart Automation",
    2.55, 0.12, 10.4, 0.54, 19, bold=True, color=WHITE)
txt(s2, "TPRM AI removes the bottlenecks of manual vendor assessments — giving your team more time to act, not analyse.",
    2.55, 0.64, 10.4, 0.30, 9.5, color=RGBColor(0xCC, 0xFF, 0xEE), italic=True)

# ── 6 feature cards — 2 col × 3 row ──────────────────────────────────────
cards = [
    ("📋", "Smart Vendor Screening", "Instant risk scoring before onboarding",
     "Automatically evaluates each vendor's sensitivity — data access, cloud usage, financial exposure — before any engagement begins.", TEAL, TEAL_LIGHT),

    ("🔍", "Automatic Document Review", "AI reads vendor documents so your team doesn't have to",
     "Upload vendor questionnaires and evidence files. The platform reads, analyses and scores them instantly — no manual page-by-page review.", TEAL, TEAL_LIGHT),

    ("⚡", "Compliance Gap Detection", "Pinpoints exactly where risks and gaps exist",
     "Compares vendor claims against Titan's policies and contracts. Flags missing controls, policy conflicts and unsupported claims automatically.", GOLD, GOLD_LIGHT),

    ("🛠", "Actionable Remediation Plans", "Clear steps to fix every risk found",
     "For every gap identified, a prioritised action plan is generated — with owners, deadlines and success criteria ready to share with vendors.", GOLD, GOLD_LIGHT),

    ("📜", "Contract Protection", "Safeguard Titan with the right contract clauses",
     "Recommends contract clauses tailored to the gaps found — covering data protection, incident response and compliance obligations.", TEAL, TEAL_LIGHT),

    ("📊", "Reports & Live Dashboard", "Audit-ready reports generated in one click",
     "Executive summaries, gap tables and action plans exported as PDF or Word. Live dashboard tracks all vendors and open risks at a glance.", TEAL, TEAL_LIGHT),
]

col_w  = 6.20
row_h  = 1.68
gap_x  = 0.20
gap_y  = 0.14
sx     = 0.27
sy     = 1.02

for i, (icon, title, oneliner, detail, ac, al) in enumerate(cards):
    col = i % 2
    row = i // 2
    cx  = sx + col * (col_w + gap_x)
    cy  = sy + row * (row_h + gap_y)

    # Card — white with colored left accent bar
    rect(s2, cx, cy, col_w, row_h, CARD_BG, lc=BORDER, lw=0.6)
    rect(s2, cx, cy, 0.07, row_h, ac)

    # Icon badge
    rect(s2, cx+0.18, cy+0.18, 0.44, 0.44, al, lc=ac, lw=0.5)
    txt(s2, icon, cx+0.18, cy+0.17, 0.44, 0.44, 13, align=PP_ALIGN.CENTER)

    # Title
    txt(s2, title, cx+0.74, cy+0.10, col_w-0.88, 0.36,
        11.5, bold=True, color=NAVY)

    # One-liner
    txt(s2, oneliner, cx+0.74, cy+0.44, col_w-0.88, 0.26,
        8.5, color=ac, italic=True)

    # Detail
    txt(s2, detail, cx+0.74, cy+0.74, col_w-0.88, 0.82,
        8.5, color=MID_TEXT)

footer(s2, 2)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 3 — IMPACT & PLATFORM STRENGTHS
# ═══════════════════════════════════════════════════════════════════════════
s3 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s3, OFF_WHITE)

# Top bar — gold accent for variety
rect(s3, 0, 0, 13.33, 0.80, NAVY)
rect(s3, 0, 0.80, 13.33, 0.05, GOLD)

rect(s3, 0.35, 0.15, 2.5, 0.34, GOLD)
txt(s3, "IMPACT & PLATFORM", 0.35, 0.15, 2.5, 0.34,
    8.5, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

txt(s3, "Built for Enterprise — Secure, Scalable & Easy to Use",
    3.10, 0.12, 9.88, 0.54, 19, bold=True, color=WHITE)
txt(s3, "Designed to fit seamlessly within Titan's existing processes and compliance standards.",
    3.10, 0.64, 9.88, 0.30, 9.5,
    color=RGBColor(0xCC, 0xDD, 0xFF), italic=True)

# ── LEFT: Business Impact panel ───────────────────────────────────────────
rect(s3, 0.27, 1.02, 5.95, 5.58, WHITE, lc=BORDER, lw=0.6)
rect(s3, 0.27, 1.02, 5.95, 0.52, TEAL)
txt(s3, "  BUSINESS IMPACT AT A GLANCE",
    0.35, 1.05, 5.75, 0.42, 11, bold=True, color=WHITE)

impacts = [
    ("80%",    "Reduction in manual assessment effort"),
    ("~10×",   "Faster vendor assessment turnaround"),
    ("100%",   "Consistent, unbiased risk scoring every time"),
    ("Zero",   "Missed gaps — AI reviews every document"),
    ("1 Platform", "For all vendor risk activities end-to-end"),
]

iy = 1.70
for num, label in impacts:
    rect(s3, 0.40, iy, 5.68, 0.76, OFF_WHITE, lc=BORDER, lw=0.4)
    rect(s3, 0.40, iy, 0.06, 0.76, TEAL)
    txt(s3, num, 0.58, iy+0.10, 1.60, 0.46,
        20, bold=True, color=TEAL)
    txt(s3, label, 2.26, iy+0.18, 3.72, 0.38,
        10, color=DARK_TEXT)
    iy += 0.88

# ── RIGHT: Platform strengths ─────────────────────────────────────────────
platform = [
    ("🔐", "Secure Access & Single Sign-On",
     "Integrates with Titan's Azure AD. Role-based access ensures the right people see the right data — with complete audit trails.",
     TEAL, TEAL_LIGHT),

    ("📧", "Instant Vendor Alerts",
     "Send risk findings directly to vendor contacts in one click. Fully formatted notifications — no manual emails required.",
     TEAL, TEAL_LIGHT),

    ("⚙️", "Admin Controls",
     "Manage users, upload Titan's internal policies as reference standards, and control all platform settings from one admin panel.",
     GOLD, GOLD_LIGHT),

    ("📈", "Live Risk Dashboard",
     "Track all active assessments, vendor risk trends and open gaps — giving leadership a clear, real-time picture of third-party exposure.",
     GOLD, GOLD_LIGHT),
]

px = 6.55
py = 1.02
pw = 6.50
ph = 1.32

for icon, title, desc, ac, al in platform:
    rect(s3, px, py, pw, ph, CARD_BG, lc=BORDER, lw=0.6)
    rect(s3, px, py, 0.07, ph, ac)

    rect(s3, px+0.18, py+0.22, 0.44, 0.44, al, lc=ac, lw=0.5)
    txt(s3, icon, px+0.18, py+0.20, 0.44, 0.44, 13, align=PP_ALIGN.CENTER)

    txt(s3, title, px+0.76, py+0.10, pw-0.90, 0.36,
        11.5, bold=True, color=NAVY)
    txt(s3, desc,  px+0.76, py+0.48, pw-0.90, 0.74,
        8.8, color=MID_TEXT)

    py += ph + 0.10

footer(s3, 3)

# ── Save ─────────────────────────────────────────────────────────────────
out = "TPRM_AI_Platform_v3_Light.pptx"
prs.save(out)
print(f"Saved: {out}")
