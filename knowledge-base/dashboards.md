# TPRM AI — Dashboards and Analytics

> **Purpose**: Dashboard logic, chart data, and analytics components for MCP retrieval.

---

## Main Dashboard (`/`)

**Template**: `webapp/templates/dashboard.html`  
**Route**: `webapp/routes/pages.py` → `GET /`  
**Auth**: Login required

### KPI Cards

| Card | Calculation | Source |
|------|-------------|--------|
| Total Assessments | `len(assessments)` | All records in `assessments` table |
| Completed | `count(status == "completed")` | assessments |
| In Progress | `count(status == "running")` | assessments |
| Pending | `count(status == "pending")` | assessments |
| Failed | `count(status == "failed")` | assessments |
| Unique Vendors Reviewed | `len({a["vendor_id"] for completed a})` | assessments with vendor_id set |

---

### Chart 1: Gap Severity Distribution (Donut/Pie)
**Data**: Across all **completed** assessments  
**Counts**: `critical`, `high`, `medium`, `low` gaps  
**Source**: `assessments.summary` JSONB column → `{critical: N, high: N, medium: N, low: N}`  
**Color coding**:
- Critical: red (`#DC2626`)
- High: orange (`#EA580C`)
- Medium: amber (`#D97706`)
- Low: green (`#059669`)

---

### Chart 2: Assessment Status Breakdown (Doughnut)
**Data**: Count per status  
**Statuses**: completed, running, pending, failed

---

### Chart 3: Top Vendors by Gap Count (Horizontal Bar)
**Data**: Up to 8 vendors, sorted descending by `total_gaps`  
**Filtered to**: Completed assessments only  
**Source**: `assessments.summary.total_gaps` per assessment  
**Labels**: `{vendor_name} ({month 'YY})`  

```python
chart_vendors = sorted(
    [
        {
            "name": a["vendor_name"],
            "gaps": a["summary"]["total_gaps"],
            "month": datetime.fromisoformat(a["created_at"]).strftime("%b '%y"),
        }
        for a in assessments
        if a["status"] == "completed" and a.get("summary")
    ],
    key=lambda x: x["gaps"],
    reverse=True,
)[:8]
```

---

### Chart 4: Assessments Created Per Month (Line/Bar — Last 12 Months)
**Data**: Count of assessments created per calendar month  
**Source**: `assessments.created_at[:7]` (e.g. "2026-05")  
**Range**: Rolling 12 months backward from current date

```python
months_data = defaultdict(int)
for a in assessments:
    months_data[a["created_at"][:7]] += 1

# Build 12-month window backward from today
chart_monthly = [{"label": "May '26", "count": 3}, ...]
```

---

### Filter Controls (Client-side)
- **Division filter**: Dropdown populated from distinct `assessments.division` values
- **Status filter**: Filter table rows by status
- **Search**: Free-text search on vendor name

---

## Assessments List Page (`/assessments`)

**Template**: `assessments_list.html`  
**Data**: All assessments (admin) or own assessments (analyst)

**Columns**:
| Column | Source |
|--------|--------|
| Vendor Name | `assessment.vendor_name` |
| Vendor ID | `assessment.vendor_id` (e.g. VND-A3F2B1) |
| Version | `assessment.version` |
| Division | `assessment.division` |
| Engagement Sensitivity | `assessment.nature_of_engagement` (high/medium/low) |
| Status | `assessment.status` |
| Created | `assessment.created_at` (displayed in IST) |
| Risk Rating | `assessment.risk_rating` (manually assigned) |
| Gaps | `assessment.summary.total_gaps` |
| Actions | View / Download PDF / Download Word |

---

## Assessment Detail Page (`/assessments/{id}`)

**Template**: `assessment_detail.html`  
**Data**: Full assessment metadata + `report_data` JSONB

### Sections displayed:

#### Header
- Vendor name, ID, version, status badge
- Created at (IST), Started at, Completed at
- Division, engagement sensitivity, SPOC email
- Overall risk rating (colour-coded badge)

#### Pre-Business Assessment Results
- Table of 10 PBA questions with Yes/No answers and scores
- Total score and derived sensitivity level

#### Executive Summary
- Text from `report_data.executive_summary`

#### Gap Analysis Summary
- Counts by severity (critical/high/medium/low)
- Table of all gaps with: control_id, type, severity, description, evidence

#### Risk Assessment
- Per-gap risk level, rationale, remediation plan

#### Remedial Plan
- Table: gap reference, action, priority, timeline, owner, acceptance criteria

#### Contract Clause Recommendations
- Existing clauses to enforce
- New clauses to add

#### Questionnaire Analysis
- Q&A breakdown by section
- Claim strength scores

#### Download buttons
- Word report (`.docx`)
- PDF report (`.pdf`)

---

## Assessment Analytics Page (`/assessment-analytics/{id}`)

**Template**: `assessment_analytics.html`

### Charts included:
1. **Severity Distribution** — pie chart of gaps by severity for this assessment
2. **Gap Types** — breakdown by `gap_type` (control_missing, policy_violation, evidence_gap, etc.)
3. **Section Coverage** — which SIG Lite sections had gaps identified
4. **Remediation Timeline** — bar chart of actions by priority (immediate/short/medium/long-term)

---

## Analytics List Page (`/analytics`)

**Template**: `analytics_list.html`  
**Auth**: Login required

### Metrics shown:
- Total assessments over time
- Gap severity trends
- Vendor risk distribution
- Most common gap types across all assessments
- Completion rate

---

## Dashboard Data API

**Endpoint**: `GET /api/analytics`  
**Response structure**:
```json
{
  "total": 42,
  "completed": 30,
  "running": 2,
  "pending": 8,
  "failed": 2,
  "unique_vendors": 18,
  "gaps_by_severity": {
    "critical": 12,
    "high": 47,
    "medium": 93,
    "low": 31
  },
  "top_vendors": [
    { "name": "Acme Corp", "gaps": 23, "month": "Mar '26" }
  ],
  "monthly_trend": [
    { "label": "Jun '25", "count": 3 },
    ...
  ],
  "divisions": ["Watches", "Jewellery", "Eyewear"]
}
```

---

## Report Generation

### Word Report (`report_generator.generate_word()`)
**Library**: `python-docx`  
**Output**: `io.BytesIO` stream

**Sections in Word report**:
1. Cover page — Titan logo, vendor name, date
2. Executive Summary
3. Pre-Business Assessment Results table
4. Gap Analysis — section-by-section breakdown
5. Risk Scoring table (gap → risk level → rationale)
6. Remedial Plan table (action, priority, timeline, owner, acceptance criteria)
7. Contract Clause Recommendations

**Styling**:
- Color: Indigo (`#4F46E5`) headers, Dark navy body text
- Severity cell shading: Red/Orange/Amber/Green
- Page margins: 2cm all sides
- Font: Calibri 10pt

### PDF Report
**Library**: ReportLab  
**Content**: Same structure as Word report  
**Logo**: `inputs/image.png` (Titan logo)

---

## Settings Admin Page (`/settings`)

**Template**: `settings.html`  
**Auth**: Admin only

| Setting | Key | Description |
|---------|-----|-------------|
| LLM Judge | `llm_judge_enabled` | Run multi-pass quality review after draft |
| LLM Cache | `llm_cache_enabled` | Reuse cached output for identical inputs |

Settings saved to `config/pipeline_settings.json` via `settings_store.save_settings()`.  
Changes take effect **immediately** without server restart.

---

## Admin Defaults Page (`/admin/defaults`)

**Template**: `admin_defaults.html`  
**Auth**: Admin only

Allows uploading organisation-wide:
- **Default policies** — stored in `default_documents` table (`doc_type = "policy"`)
- **Default contract clauses** — stored in `default_documents` table (`doc_type = "clause"`)

These are loaded into every assessment pipeline as the baseline compliance reference.
