"""
Run the full TPRM AI pipeline locally against the FastAPI server.

Usage:
    python scripts/run_pipeline.py --base-url http://127.0.0.1:8085
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

API_KEY = "your_development_secret_key"
HEADERS = {"X-API-Key": API_KEY}
TIMEOUT = httpx.Timeout(300.0)  # 5 min for long LLM calls

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def api(method: str, url: str, client: httpx.Client, **kwargs):
    """Make an API call with error reporting."""
    resp = client.request(method, url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    if resp.status_code >= 400:
        print(f"  ERROR {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8085")
    args = parser.parse_args()
    base = args.base_url

    client = httpx.Client()

    # ── Health check ─────────────────────────────────────
    print("=" * 60)
    print("TPRM AI Pipeline Runner")
    print("=" * 60)
    r = api("GET", f"{base}/health", client)
    print(f"[OK] Server healthy: {r.json()}")

    # ── Step 1: Create vendor ────────────────────────────
    print("\n--- Step 1: Create Vendor ---")
    r = api("POST", f"{base}/api/v1/vendors", client,
            json={"name": "Adobe", "domain": "adobe.com"})
    vendor = r.json()
    vendor_id = vendor["id"]
    print(f"[OK] Vendor created: {vendor['name']} (id={vendor_id})")

    # ── Step 2: Create assessment ────────────────────────
    print("\n--- Step 2: Create Assessment ---")
    r = api("POST", f"{base}/api/v1/assessments", client,
            json={"vendor_id": vendor_id})
    assessment = r.json()
    assessment_id = assessment["id"]
    print(f"[OK] Assessment created: id={assessment_id}, status={assessment['status']}")

    # ── Step 3: Upload policies ──────────────────────────
    print("\n--- Step 3: Upload Policies ---")
    policy_dir = DATA_DIR / "policies"
    for fpath in sorted(policy_dir.iterdir()):
        if fpath.suffix.lower() in (".pdf", ".docx", ".txt"):
            print(f"  Uploading policy: {fpath.name}")
            with open(fpath, "rb") as f:
                r = api("POST", f"{base}/api/v1/policies", client,
                        data={"title": fpath.stem, "version": "1.0"},
                        files={"file": (fpath.name, f, "application/octet-stream")})
            print(f"  [OK] Policy uploaded: {r.json().get('id')}")

    # ── Step 4: Upload contract clauses ──────────────────
    print("\n--- Step 4: Upload Contract Clauses ---")
    clauses_dir = DATA_DIR / "contracts"
    for fpath in sorted(clauses_dir.iterdir()):
        if fpath.suffix.lower() in (".pdf", ".docx", ".txt"):
            print(f"  Uploading clause: {fpath.name}")
            with open(fpath, "rb") as f:
                r = api("POST", f"{base}/api/v1/contract-clauses", client,
                        data={"category": fpath.stem, "standard_clause": "true"},
                        files={"file": (fpath.name, f, "application/octet-stream")})
            print(f"  [OK] Clause uploaded: {r.json().get('id')}")

    # ── Step 5: Upload questionnaire ─────────────────────
    print("\n--- Step 5: Upload Questionnaire ---")
    q_file = DATA_DIR / "questionnaires" / "Adobe_Cloud - 2023 SIG Lite - 1.0.pdf"
    with open(q_file, "rb") as f:
        r = api("POST", f"{base}/api/v1/assessments/{assessment_id}/questionnaires",
                client, files={"file": (q_file.name, f, "application/pdf")})
    q_result = r.json()
    print(f"[OK] Questionnaire: status={q_result['status']}, task_id={q_result['task_id']}")

    # ── Step 6: Upload artifacts ─────────────────────────
    print("\n--- Step 6: Upload Artifacts ---")
    artifact_dir = DATA_DIR / "artifacts"
    pdf_files = sorted([f for f in artifact_dir.iterdir() if f.suffix.lower() == ".pdf"])
    total = len(pdf_files)
    for i, fpath in enumerate(pdf_files, 1):
        print(f"  [{i}/{total}] Uploading: {fpath.name}")
        with open(fpath, "rb") as f:
            r = api("POST", f"{base}/api/v1/assessments/{assessment_id}/artifacts",
                    client, files={"file": (fpath.name, f, "application/pdf")})
        a_result = r.json()
        print(f"    [OK] status={a_result['status']}")

    # ── Step 7: Trigger full analysis pipeline ───────────
    print("\n--- Step 7: Trigger Full Analysis Pipeline ---")
    print("  Running gap analysis → risk assessment → recommendations...")
    print("  (This may take several minutes due to LLM calls)")
    start = time.time()
    r = api("POST", f"{base}/api/v1/assessments/{assessment_id}/analyze", client)
    elapsed = time.time() - start
    analysis_result = r.json()
    print(f"[OK] Analysis: status={analysis_result['status']} ({elapsed:.1f}s)")

    # ── Step 8: Check assessment status ──────────────────
    print("\n--- Step 8: Assessment Status ---")
    r = api("GET", f"{base}/api/v1/assessments/{assessment_id}/status", client)
    status_data = r.json()
    print(f"[OK] Assessment status: {status_data['status']}")

    # ── Step 9: Retrieve gaps ────────────────────────────
    print("\n--- Step 9: Gaps Found ---")
    r = api("GET", f"{base}/api/v1/assessments/{assessment_id}/gaps", client)
    gaps = r.json()
    print(f"[OK] {len(gaps)} gaps identified")
    for g in gaps[:5]:
        print(f"  - [{g['severity']}] {g['gap_type']}: {g['description'][:80]}...")

    # ── Step 10: Retrieve risks ──────────────────────────
    print("\n--- Step 10: Risks Scored ---")
    r = api("GET", f"{base}/api/v1/assessments/{assessment_id}/risks", client)
    risks = r.json()
    print(f"[OK] {len(risks)} risks scored")
    for rk in risks[:5]:
        print(f"  - [{rk['risk_level']}] {rk['rationale'][:80]}...")

    # ── Step 11: Retrieve full report ────────────────────
    print("\n--- Step 11: Full Assessment Report ---")
    r = api("GET", f"{base}/api/v1/assessments/{assessment_id}/report", client)
    report = r.json()

    print(f"\n{'=' * 60}")
    print(f"ASSESSMENT REPORT")
    print(f"{'=' * 60}")
    print(f"Vendor:          {report['vendor']['name']} ({report['vendor'].get('domain', 'N/A')})")
    print(f"Assessment ID:   {report['assessment']['id']}")
    print(f"Status:          {report['assessment']['status']}")
    print(f"Questionnaires:  {len(report.get('questionnaire_insights', []))}")
    print(f"Questions:       {len(report.get('questions', []))}")
    print(f"Artifacts:       {len(report.get('artifacts', []))}")
    print(f"Gaps:            {len(report.get('gaps', []))}")
    print(f"Risks:           {len(report.get('risks', []))}")
    print(f"Recommendations: {len(report.get('recommendations', []))}")

    # Print gap summary
    if report.get("gaps"):
        print(f"\n--- Gap Summary ---")
        severity_counts = {}
        for g in report["gaps"]:
            sev = g.get("severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        for sev, count in sorted(severity_counts.items()):
            print(f"  {sev}: {count}")

    # Print risk summary
    if report.get("risks"):
        print(f"\n--- Risk Summary ---")
        level_counts = {}
        for r in report["risks"]:
            lvl = r.get("risk_level", "unknown")
            level_counts[lvl] = level_counts.get(lvl, 0) + 1
        for lvl, count in sorted(level_counts.items()):
            print(f"  {lvl}: {count}")

    # Print recommendations
    if report.get("recommendations"):
        print(f"\n--- Top Recommendations ---")
        for rec in report["recommendations"][:5]:
            print(f"  * {rec.get('clause_text', '')[:100]}...")
            print(f"    Justification: {rec.get('justification', '')[:100]}")

    # Save full report to file
    report_path = Path(__file__).resolve().parent.parent / "output" / "assessment_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n[OK] Full report saved to: {report_path}")

    print(f"\n{'=' * 60}")
    print("Pipeline completed successfully!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
