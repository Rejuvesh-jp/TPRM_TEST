"""
Backfill Open-Gap Summary Counts
================================
One-time, idempotent repair for assessments whose gaps were closed *before*
the summary counts were changed to exclude closed gaps.

Those rows still have ``summary.total_gaps`` (and ``summary.gap_severity``)
computed over all gaps, including closed ones, so the dashboard / assessments
list / analytics cards keep showing the pre-close number until the next edit
to the report. This script recomputes the derived summary counts from
``report_data`` so historical rows match the new behaviour.

Only derived summary fields are rewritten. Gaps, recommendations and remedial
actions are never modified.

Usage (from the project root, with the venv active):

    # Report what would change, write nothing:
    python -m scripts.backfill_open_gap_counts

    # Apply the changes:
    python -m scripts.backfill_open_gap_counts --apply
"""
import argparse
import sys
from collections import Counter

from sqlalchemy import select

from webapp.db import get_session
from webapp.models import Assessment


def _open_gaps(report: dict) -> list:
    """Gaps that are still open. Missing gap_status means open."""
    return [g for g in report.get("gaps", []) if g.get("gap_status", "open") == "open"]


def _expected_summary(report: dict) -> dict:
    """The summary counts _refresh_summary() would produce for this report."""
    open_gaps = _open_gaps(report)
    return {
        "gap_severity": dict(Counter(g.get("severity", "medium") for g in open_gaps)),
        "total_gaps": len(open_gaps),
        "total_remedial_actions": len(report.get("remedial_plan", [])),
        "total_recommendations": len(report.get("recommendations", [])),
    }


def backfill(apply_changes: bool) -> int:
    """Recompute summary counts. Returns the number of assessments changed."""
    changed = 0
    scanned = 0

    with get_session() as session:
        assessments = session.scalars(
            select(Assessment).order_by(Assessment.created_at.asc())
        ).all()

        for a in assessments:
            report = a.report_data
            if not isinstance(report, dict) or "gaps" not in report:
                continue
            scanned += 1

            expected = _expected_summary(report)
            current = report.get("summary") or {}
            diff = {
                key: (current.get(key), value)
                for key, value in expected.items()
                if current.get(key) != value
            }
            if not diff:
                continue

            changed += 1
            closed = len(report.get("gaps", [])) - expected["total_gaps"]
            print(f"\n{a.vendor_name} (v{a.version}) — {a.id}")
            print(f"  closed gaps in report: {closed}")
            for key, (old, new) in diff.items():
                print(f"  {key}: {old!r} -> {new!r}")

            if apply_changes:
                # Rebuild the dicts so SQLAlchemy detects the JSONB change
                new_report = dict(report)
                new_report["summary"] = {**current, **expected}
                a.report_data = new_report
                a.summary = new_report["summary"]

        if apply_changes:
            session.commit()
        else:
            session.rollback()

    print(f"\nScanned {scanned} assessment(s) with report data.")
    if changed == 0:
        print("All summary counts already correct — nothing to do.")
    elif apply_changes:
        print(f"Updated {changed} assessment(s).")
    else:
        print(f"{changed} assessment(s) would be updated. "
              f"Re-run with --apply to write the changes.")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the recomputed counts. Without this flag the script only reports.",
    )
    args = parser.parse_args()
    backfill(apply_changes=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
