from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from lxml import etree

# ── Enterprise Dark Theme — Pure Teal/Navy, No Gold ──────────────────────
BG          = RGBColor(0x07, 0x12, 0x24)   # deepest navy
PANEL       = RGBColor(0x04, 0x0D, 0x1A)   # near-black panel
CARD        = RGBColor(0x0C, 0x22, 0x3A)   # card base
CARD_LITE   = RGBColor(0x10, 0x2C, 0x4A)   # card highlight band
TEAL        = RGBColor(0x00, 0xE5, 0xB8)   # vivid teal
TEAL_MED    = RGBColor(0x00, 0xA8, 0x88)   # mid teal
TEAL_DIM    = RGBColor(0x00, 0x60, 0x50)   # dark teal fill
TEAL_GLOW   = RGBColor(0x00, 0x30, 0x28)   # glow backdrop
TEAL_MUTED  = RGBColor(0x00, 0x78, 0x62)   # muted accent
RULE        = RGBColor(0x0E, 0x2E, 0x4E)   # separator line
WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
BRIGHT      = RGBColor(0xE8, 0xF8, 0xFF)   # near-white text
BODY        = RGBColor(0x9B, 0xB8, 0xCE)   # body text
DIM         = RGBColor(0x55, 0x72, 0x88)   # footer / caption

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

def oval(slide, x, y, w, h, fill, lc=None, lw=0.5):
    s = slide.shapes.add_shape(9, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if lc:
        s.line.color.rgb = lc
        s.line.width = Pt(lw)
    else:
        s.line.fill.background()
    return s

def rotated_rect(slide, x, y, w, h, fill, angle):
    s = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    s.rotation = angle
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

def gloss_card(slide, x, y, w, h, accent=TEAL):
    """Card with glossy top-highlight band and teal top-edge line."""
    rect(slide, x, y, w, h, CARD)
    # subtle lighter band at top 30% — simulates gloss
    rect(slide, x, y, w, h * 0.30, CARD_LITE)
    # bright teal top-edge line
    rect(slide, x, y, w, 0.04, accent)
    # left glow strip
    rect(slide, x, y, 0.05, h, TEAL_DIM)
    # very subtle right shadow strip
    rect(slide, x + w - 0.03, y, 0.03, h, PANEL)

def stat_block(slide, x, y, w, h, number, label):
    """Glossy impact stat tile."""
    rect(slide, x, y, w, h, CARD)
    rect(slide, x, y, w, h * 0.28, CARD_LITE)
    rect(slide, x, y, w, 0.04, TEAL)
    # glow oval behind number
    oval(slide, x + w/2 - 0.55, y + 0.06, 1.10, 0.62, TEAL_GLOW)
    txt(slide, number, x + 0.05, y + 0.06, w - 0.10, 0.56,
        26, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    rect(slide, x + 0.15, y + 0.64, w - 0.30, 0.025, TEAL_DIM)
    txt(slide, label, x + 0.08, y + 0.72, w - 0.16, 0.50,
        8.5, color=BODY, align=PP_ALIGN.CENTER)

def footer(slide, num):
    rect(slide, 0, 6.87, 13.33, 0.63, PANEL)
    rect(slide, 0, 6.87, 13.33, 0.03, TEAL)
    # left teal dot
    oval(slide, 0.32, 6.97, 0.12, 0.12, TEAL)
    txt(slide, "CONFIDENTIAL  |  Titan Company Limited  |  2025",
        0, 6.97, 13.33, 0.36, 7.5, color=DIM, align=PP_ALIGN.CENTER)
    # page pill
    rect(slide, 12.55, 6.93, 0.50, 0.28, TEAL_DIM, lc=TEAL, lw=0.5)
    txt(slide, f"0{num}", 12.55, 6.93, 0.50, 0.28, 8.5,
        bold=True, color=TEAL, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ═══════════════════════════════════════════════════════════════════════════
s1 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s1, BG)

# ── full-bleed dark left panel
rect(s1, 0, 0, 6.10, 7.5, PANEL)

# ── large rotated teal diagonal slash — creative divider
rotated_rect(s1, 5.20, -1.0, 1.60, 10.0, TEAL_DIM, 8)
rotated_rect(s1, 5.55, -1.0, 0.18, 10.0, TEAL,     8)

# ── top teal accent bar (left panel)
rect(s1, 0, 0, 6.10, 0.10, TEAL)

# ── top-right corner teal bar matching
rect(s1, 6.10, 0, 7.23, 0.10, TEAL_DIM)

# ── decorative concentric arc rings (top-left corner)
for r_size, r_color in [(2.8, TEAL_GLOW), (2.2, RGBColor(0x00,0x25,0x20)),
                         (1.5, TEAL_DIM), (0.7, TEAL_MUTED)]:
    oval(s1, -r_size/2, -r_size/2, r_size, r_size, r_color)

# ── fine dot grid — left panel only
for gx in [0.55, 1.30, 2.05, 2.80, 3.55, 4.30, 5.05]:
    for gy in [1.20, 2.10, 3.00, 3.90, 4.80, 5.70]:
        oval(s1, gx, gy, 0.028, 0.028, TEAL_MUTED)

# ── Company label
rect(s1, 0.38, 0.24, 0.04, 0.32, TEAL)   # left accent pip
txt(s1, "TITAN COMPANY LIMITED", 0.52, 0.24, 5.0, 0.32,
    8, bold=True, color=TEAL)
txt(s1, "A TITAN COMPANY INITIATIVE", 0.52, 0.54, 5.0, 0.26,
    7, color=BODY, italic=True)

# ── Main title — large, impactful
txt(s1, "TPRM AI", 0.38, 0.95, 5.5, 1.20, 64, bold=True, color=WHITE)

# Teal glowing underline on title
rect(s1, 0.38, 2.08, 3.20, 0.07, TEAL)
rect(s1, 0.38, 2.08, 3.20, 0.02, WHITE)   # gloss on line

txt(s1, "Assessment Platform", 0.38, 2.22, 5.5, 0.55,
    22, color=TEAL)

# ── Sub-tagline
txt(s1,
    "Assess vendor risks in minutes, not weeks.\n"
    "Automatically identify gaps, generate action plans\n"
    "and produce audit-ready reports — all in one place.",
    0.38, 2.90, 5.45, 1.05, 10.5, color=BODY)

# ── 3 stat tiles — horizontal
sx = 0.38
for top, bot in [("80%","Less Manual\nEffort"), ("Minutes","Not Weeks"), ("Auto","Reports\n& Action Plans")]:
    rect(s1, sx, 4.12, 1.72, 0.96, CARD)
    rect(s1, sx, 4.12, 1.72, 0.25, CARD_LITE)
    rect(s1, sx, 4.12, 1.72, 0.04, TEAL)
    oval(s1, sx + 0.58, 4.14, 0.56, 0.30, TEAL_GLOW)
    txt(s1, top, sx+0.08, 4.13, 1.56, 0.36, 16,
        bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    txt(s1, bot, sx+0.08, 4.48, 1.56, 0.50, 7.5,
        color=BODY, align=PP_ALIGN.CENTER)
    sx += 1.82

# ── "AI-Powered" label badge
rect(s1, 0.38, 5.26, 2.55, 0.34, TEAL_DIM, lc=TEAL, lw=0.7)
oval(s1, 0.50, 5.33, 0.18, 0.18, TEAL)
txt(s1, "  AI-POWERED RISK INTELLIGENCE", 0.52, 5.27, 2.42, 0.32,
    7.5, bold=True, color=TEAL)

# ── RIGHT: screenshot panel
# Glow aura behind frame
rect(s1, 6.18, 0.55, 6.92, 5.72, TEAL_GLOW)
# Outer teal frame
rect(s1, 6.24, 0.60, 6.80, 5.62, TEAL, lc=TEAL, lw=1.2)
# Inner dark mat
rect(s1, 6.32, 0.68, 6.64, 5.46, BG)

try:
    s1.shapes.add_picture(
        "inputs/image.png",
        Inches(6.32), Inches(0.68),
        Inches(6.64), Inches(5.46)
    )
except Exception:
    txt(s1, "[App Screenshot]", 6.32, 3.0, 6.64, 0.8,
        12, color=DIM, align=PP_ALIGN.CENTER)

# gloss reflection band over screenshot bottom
rect(s1, 6.32, 5.72, 6.64, 0.42, PANEL)
rect(s1, 6.32, 5.72, 6.64, 0.02, TEAL_DIM)
txt(s1, "TPRM AI Platform  —  Live Dashboard View",
    6.32, 5.78, 6.64, 0.28, 7.5,
    color=DIM, italic=True, align=PP_ALIGN.CENTER)

footer(s1, 1)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 2 — HOW IT HELPS
# ═══════════════════════════════════════════════════════════════════════════
s2 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s2, BG)

# ── Header band
rect(s2, 0, 0, 13.33, 1.08, PANEL)
rect(s2, 0, 0, 13.33, 0.06, TEAL)
rect(s2, 0, 1.02, 13.33, 0.06, TEAL_DIM)

# Decorative corner rings — top right
for r_size, r_col in [(3.0, TEAL_GLOW), (2.2, RGBColor(0x00,0x1E,0x18))]:
    oval(s2, 13.33 - r_size/2, -r_size/2, r_size, r_size, r_col)

# Label pill
rect(s2, 0.35, 0.18, 2.15, 0.34, TEAL_DIM, lc=TEAL, lw=0.7)
oval(s2, 0.46, 0.27, 0.14, 0.14, TEAL)
txt(s2, "  HOW IT HELPS", 0.44, 0.18, 2.05, 0.34,
    8.5, bold=True, color=TEAL)

txt(s2, "From Weeks of Manual Work to Minutes of Smart Automation",
    2.70, 0.12, 10.35, 0.56, 20, bold=True, color=WHITE)
txt(s2, "TPRM AI removes bottlenecks of manual vendor assessments — giving your team more time to act, not analyse.",
    2.70, 0.66, 10.35, 0.30, 9.5, color=TEAL, italic=True)

# ── 6 glossy feature cards — 2 col × 3 row ──────────────────────────────
cards = [
    ("📋", "Smart Vendor Screening",
     "Instant risk scoring before onboarding",
     "Automatically evaluates each vendor's sensitivity — data access, cloud usage, financial exposure — before any engagement begins."),
    ("🔍", "Automatic Document Review",
     "AI reads vendor documents so your team doesn't have to",
     "Upload questionnaires and evidence files. The platform reads, analyses and scores them instantly — no manual review needed."),
    ("⚡", "Compliance Gap Detection",
     "Pinpoints exactly where risks and gaps exist",
     "Compares vendor claims against Titan's policies and contracts. Flags missing controls, policy conflicts and unsupported claims automatically."),
    ("🛠", "Actionable Remediation Plans",
     "Clear steps to fix every risk found",
     "For every gap identified, a prioritised action plan is generated — with owners, deadlines and success criteria ready to share."),
    ("📜", "Contract Protection",
     "Safeguard Titan with the right contract clauses",
     "Recommends contract clauses tailored to gaps found — covering data protection, incident response and compliance obligations."),
    ("📊", "Reports & Live Dashboard",
     "Audit-ready reports generated in one click",
     "Executive summaries and gap tables exported as PDF or Word. Live dashboard tracks all vendors and open risks at a glance."),
]

CW = 6.24
CH = 1.70
GX = 0.20
GY = 0.16
OX = 0.27
OY = 1.16

for i, (icon, title, oneliner, detail) in enumerate(cards):
    col = i % 2
    row = i // 2
    cx  = OX + col * (CW + GX)
    cy  = OY + row * (CH + GY)

    gloss_card(s2, cx, cy, CW, CH)

    # Icon — oval badge with glow
    oval(s2, cx+0.24, cy+0.14, 0.54, 0.54, TEAL_GLOW)
    oval(s2, cx+0.28, cy+0.18, 0.46, 0.46, TEAL_DIM, lc=TEAL, lw=0.6)
    txt(s2, icon, cx+0.28, cy+0.17, 0.46, 0.46, 14, align=PP_ALIGN.CENTER)

    # Number badge top-right
    oval(s2, cx+CW-0.42, cy+0.10, 0.30, 0.30, TEAL_DIM)
    txt(s2, str(i+1), cx+CW-0.42, cy+0.09, 0.30, 0.30,
        8, bold=True, color=TEAL, align=PP_ALIGN.CENTER)

    # Title
    txt(s2, title, cx+0.86, cy+0.10, CW-1.36, 0.36,
        11.5, bold=True, color=BRIGHT)

    # One-liner
    txt(s2, oneliner, cx+0.86, cy+0.44, CW-1.36, 0.26,
        8.5, color=TEAL, italic=True)

    # Thin rule
    rect(s2, cx+0.86, cy+0.72, CW-0.98, 0.02, RULE)

    # Detail
    txt(s2, detail, cx+0.86, cy+0.78, CW-1.00, 0.82,
        8.5, color=BODY)

footer(s2, 2)

# ═══════════════════════════════════════════════════════════════════════════
# SLIDE 3 — IMPACT & PLATFORM  (pure teal theme — no gold)
# ═══════════════════════════════════════════════════════════════════════════
s3 = prs.slides.add_slide(prs.slide_layouts[6])
bg(s3, BG)

# ── Header — exactly matching slide 2 style
rect(s3, 0, 0, 13.33, 1.08, PANEL)
rect(s3, 0, 0, 13.33, 0.06, TEAL)
rect(s3, 0, 1.02, 13.33, 0.06, TEAL_DIM)

# Decorative rings — top left
for r_size, r_col in [(3.0, TEAL_GLOW), (2.2, RGBColor(0x00,0x1E,0x18))]:
    oval(s3, -r_size/2, -r_size/2, r_size, r_size, r_col)

# Label pill — teal (matching slide 2)
rect(s3, 0.35, 0.18, 2.35, 0.34, TEAL_DIM, lc=TEAL, lw=0.7)
oval(s3, 0.46, 0.27, 0.14, 0.14, TEAL)
txt(s3, "  IMPACT & PLATFORM", 0.44, 0.18, 2.25, 0.34,
    8.5, bold=True, color=TEAL)

txt(s3, "Built for Enterprise — Secure, Scalable & Always Ready",
    2.90, 0.12, 10.10, 0.56, 20, bold=True, color=WHITE)
txt(s3, "Designed to fit seamlessly within Titan's existing processes, governance and compliance standards.",
    2.90, 0.66, 10.10, 0.30, 9.5, color=TEAL, italic=True)

# ── LEFT: 5 impact stat tiles (2-col mini grid) ───────────────────────────
# Section label
rect(s3, 0.27, 1.16, 6.0, 0.44, TEAL_DIM, lc=TEAL, lw=0.6)
rect(s3, 0.27, 1.16, 0.06, 0.44, TEAL)
oval(s3, 0.44, 1.25, 0.26, 0.26, TEAL)
txt(s3, "  BUSINESS IMPACT AT A GLANCE",
    0.50, 1.19, 5.60, 0.38, 10, bold=True, color=WHITE)

stats_data = [
    ("80%",    "Less Manual\nEffort"),
    ("~10×",   "Faster\nAssessments"),
    ("100%",   "Consistent\nRisk Scoring"),
    ("Zero",   "Missed\nGaps"),
    ("1 Hub",  "All Vendor Risk\nActivities"),
]

# 3 tiles row 1, 2 tiles row 2 (centered)
positions_r1 = [(0.27, 1.70), (2.27, 1.70), (4.27, 1.70)]
positions_r2 = [(1.27, 3.14), (3.27, 3.14)]
all_positions = positions_r1 + positions_r2
TW, TH = 1.82, 1.28

for idx, ((tx, ty), (num, lbl)) in enumerate(zip(all_positions, stats_data)):
    rect(s3, tx, ty, TW, TH, CARD)
    rect(s3, tx, ty, TW, TH * 0.28, CARD_LITE)
    rect(s3, tx, ty, TW, 0.04, TEAL)
    oval(s3, tx + TW/2 - 0.50, ty + 0.06, 1.00, 0.54, TEAL_GLOW)
    txt(s3, num, tx+0.05, ty+0.06, TW-0.10, 0.50,
        24, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    rect(s3, tx+0.18, ty+0.62, TW-0.36, 0.022, TEAL_DIM)
    txt(s3, lbl, tx+0.06, ty+0.70, TW-0.12, 0.50,
        8.5, color=BODY, align=PP_ALIGN.CENTER)

# ── RIGHT: 4 glossy platform cards (matching slide 2 card style) ──────────
platform = [
    ("🔐", "Secure Access & Single Sign-On",
     "Integrates with Titan's Azure AD. Role-based access ensures the right people see the right data — with complete audit trails."),
    ("📧", "Instant Vendor Alerts",
     "Send risk findings directly to vendor contacts in one click. Fully formatted notifications — no manual emails required."),
    ("⚙️", "Admin & Pipeline Controls",
     "Manage users, upload Titan's internal policies as reference standards, toggle AI features and control all platform settings."),
    ("📈", "Live Risk Dashboard",
     "Track all active assessments, vendor risk trends and open gaps — giving leadership a real-time picture of third-party exposure."),
]

PX = 6.55
PY = 1.16
PW = 6.50
PH = 1.32
PG = 0.10

for j, (icon, title, desc) in enumerate(platform):
    cy = PY + j * (PH + PG)

    gloss_card(s3, PX, cy, PW, PH)

    # Icon oval badge
    oval(s3, PX+0.24, cy+0.16, 0.52, 0.52, TEAL_GLOW)
    oval(s3, PX+0.28, cy+0.20, 0.44, 0.44, TEAL_DIM, lc=TEAL, lw=0.6)
    txt(s3, icon, PX+0.28, cy+0.19, 0.44, 0.44, 13, align=PP_ALIGN.CENTER)

    # Number badge top-right
    oval(s3, PX+PW-0.42, cy+0.10, 0.30, 0.30, TEAL_DIM)
    txt(s3, str(j+1), PX+PW-0.42, cy+0.09, 0.30, 0.30,
        8, bold=True, color=TEAL, align=PP_ALIGN.CENTER)

    # Title
    txt(s3, title, PX+0.86, cy+0.10, PW-1.36, 0.36,
        11.5, bold=True, color=BRIGHT)

    # Thin rule
    rect(s3, PX+0.86, cy+0.50, PW-0.98, 0.02, RULE)

    # Desc
    txt(s3, desc, PX+0.86, cy+0.58, PW-1.00, 0.64,
        8.8, color=BODY)

footer(s3, 3)

# ── Save ─────────────────────────────────────────────────────────────────
out = "TPRM_AI_v4_Enterprise.pptx"
prs.save(out)
print(f"Saved: {out}")
