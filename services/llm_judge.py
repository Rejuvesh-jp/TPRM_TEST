"""
LLM Judge Service
=================
Runs multiple iterative LLM review passes on the draft assessment output.

Each iteration:
  1. Reviews the CURRENT state of gaps/recommendations/remedial actions
  2. Returns structured correction JSON
  3. Corrections are applied immediately
  4. The next iteration reviews the CORRECTED output

This converges toward a stable, high-quality assessment because:
  - Pass 1: catches obvious duplicates, severity mismatches, weak wording
  - Pass 2: catches any new inconsistencies introduced by pass-1 corrections
  - Pass 3: final polish — typically returns empty/minimal corrections

The judge does NOT regenerate gaps from scratch — it only flags issues in:
  - Duplicate gaps (same root cause, different wording)
  - Unsupported gaps (claimed without questionnaire/artifact backing)
  - Missing controls (critical controls clearly present in evidence but not flagged)
  - Severity misalignments
  - Clause irrelevance in recommendations
  - Vague recommendation wording
  - Summary/findings contradictions

The caller (pipeline_runner) invokes `run_llm_judge_multi_pass` which handles
all iterations internally and returns the final merged result.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger("tprm.judge")

# ── Load judge prompt from YAML ─────────────────────────────────────────────────
_PROMPT_FILE = Path(__file__).parent.parent / "app" / "prompts" / "llm_judge.yaml"


def _load_judge_prompts() -> tuple[str, str]:
    """Return (system_prompt, user_template) from llm_judge.yaml."""
    try:
        import yaml
        with open(_PROMPT_FILE, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        return doc.get("system", "").strip(), doc.get("user", "").strip()
    except Exception as exc:
        logger.error("Could not load llm_judge.yaml: %s", exc)
        return (
            "You are a TPRM quality reviewer. Review the draft assessment for quality issues.",
            "DRAFT ASSESSMENT:\n{{draft_gaps}}\nReturn JSON with duplicate_gaps, unsupported_gaps, "
            "missing_controls, severity_issues, clause_issues, recommendation_improvements, summary_issues.",
        )


def _render_judge_prompt(
    vendor_name: str,
    gaps: list[dict],
    recommendations: list[dict],
    remedial_actions: list[dict],
    all_questions: list[dict],
    artifacts: list[dict],
    overall_risk_rating: str,
) -> tuple[str, str]:
    """Render the judge system and user prompts."""
    system_prompt, user_template = _load_judge_prompts()

    # Compact representation of questionnaire claims
    q_insights = []
    for q in all_questions[:60]:  # cap to keep prompt manageable
        q_insights.append({
            "control_id": q.get("control_id"),
            "question": (q.get("question_text") or "")[:120],
            "response": (q.get("response_text") or "")[:120],
            "claim_strength": q.get("claim_strength"),
        })

    # Compact artifact evidence summary (just file names and chunk counts)
    art_summary = [
        {"file": a.get("file_name"), "chunks": len(a.get("chunks", []))}
        for a in artifacts
    ]

    # Compact gaps representation for the prompt
    compact_gaps = []
    for g in gaps:
        compact_gaps.append({
            "id": g.get("id") or g.get("gap_id", ""),
            "control_id": g.get("control_id", ""),
            "gap_type": g.get("gap_type", ""),
            "severity": g.get("severity", ""),
            "confidence": g.get("confidence"),
            "description": (g.get("description") or "")[:200],
            "source_refs": g.get("source_refs", {}),
        })

    # Compact recommendations
    compact_recs = []
    for r in recommendations[:30]:
        compact_recs.append({
            "id": r.get("id") or r.get("recommendation_id", ""),
            "clause_text": (r.get("clause_text") or "")[:100],
            "justification": (r.get("justification") or "")[:150],
            "priority": r.get("priority"),
        })

    # Compact remedial actions
    compact_actions = []
    for a in remedial_actions[:30]:
        compact_actions.append({
            "id": a.get("id") or a.get("action_id", ""),
            "action": (a.get("action") or a.get("recommendation") or "")[:150],
            "priority": a.get("priority"),
        })

    user_prompt = (
        user_template
        .replace("{{vendor_name}}", vendor_name or "Unknown")
        .replace("{{questionnaire_insights}}", json.dumps(q_insights, indent=2)[:6000])
        .replace("{{artifact_evidence_summary}}", json.dumps(art_summary)[:1000])
        .replace("{{total_gaps}}", str(len(gaps)))
        .replace("{{draft_gaps}}", json.dumps(compact_gaps, indent=2)[:8000])
        .replace("{{total_recommendations}}", str(len(recommendations)))
        .replace("{{draft_recommendations}}", json.dumps(compact_recs, indent=2)[:3000])
        .replace("{{total_remedial_actions}}", str(len(remedial_actions)))
        .replace("{{draft_remedial_actions}}", json.dumps(compact_actions, indent=2)[:2000])
        .replace("{{overall_risk_rating}}", overall_risk_rating or "unknown")
    )

    return system_prompt, user_prompt


def run_llm_judge(
    vendor_name: str,
    gaps: list[dict],
    recommendations: list[dict],
    remedial_actions: list[dict],
    all_questions: list[dict],
    artifacts: list[dict],
    overall_risk_rating: str,
    llm_fn,
) -> dict:
    """
    Run the LLM judge against the draft assessment output.

    Returns a dict with keys:
        duplicate_gaps, unsupported_gaps, missing_controls,
        severity_issues, clause_issues, recommendation_improvements,
        summary_issues
    All values are lists; empty if no issues found.
    """
    _empty = {
        "duplicate_gaps": [],
        "unsupported_gaps": [],
        "missing_controls": [],
        "severity_issues": [],
        "clause_issues": [],
        "recommendation_improvements": [],
        "summary_issues": [],
    }

    if not gaps:
        logger.info("Judge skipped — no gaps to review")
        return _empty

    try:
        system_prompt, user_prompt = _render_judge_prompt(
            vendor_name, gaps, recommendations, remedial_actions,
            all_questions, artifacts, overall_risk_rating,
        )
        result = llm_fn(user_prompt, system_prompt=system_prompt)
        if not isinstance(result, dict):
            logger.warning("Judge returned non-dict: %r", str(result)[:100])
            return _empty
        # Ensure all expected keys exist
        for key in _empty:
            if key not in result:
                result[key] = []
        logger.info(
            "Judge complete: %d duplicates, %d unsupported, %d missing_controls, "
            "%d severity_issues, %d clause_issues, %d rec_improvements, %d summary_issues",
            len(result["duplicate_gaps"]),
            len(result["unsupported_gaps"]),
            len(result["missing_controls"]),
            len(result["severity_issues"]),
            len(result["clause_issues"]),
            len(result["recommendation_improvements"]),
            len(result["summary_issues"]),
        )
        return result
    except Exception as exc:
        logger.error("LLM judge failed: %s", exc)
        return _empty


# ── Number of judge iterations (configurable) ────────────────────────────────
JUDGE_ITERATIONS = 3


def _merge_judge_results(base: dict, addition: dict) -> dict:
    """Merge a new judge pass result into the cumulative result.

    Lists are extended (not replaced) — but we deduplicate by gap_id / recommendation_id
    to avoid flagging the same item twice across passes.
    """
    merged = {}
    for key in base:
        base_list = base.get(key, [])
        add_list = addition.get(key, [])
        if not add_list:
            merged[key] = base_list
            continue

        # Build a set of identity keys already present to avoid duplicates
        seen: set[str] = set()
        for item in base_list:
            if isinstance(item, dict):
                # Use the most discriminating ID available
                ident = (
                    str(item.get("gap_id", ""))
                    or str(item.get("recommendation_id", ""))
                    or str(item.get("gap_ids", ""))
                    or str(item.get("control_id", ""))
                    or str(item.get("issue", ""))[:80]
                )
                seen.add(ident)

        new_items = []
        for item in add_list:
            if isinstance(item, dict):
                ident = (
                    str(item.get("gap_id", ""))
                    or str(item.get("recommendation_id", ""))
                    or str(item.get("gap_ids", ""))
                    or str(item.get("control_id", ""))
                    or str(item.get("issue", ""))[:80]
                )
                if ident and ident in seen:
                    continue
                seen.add(ident)
            new_items.append(item)

        merged[key] = base_list + new_items
    return merged


def _count_issues(result: dict) -> int:
    """Count total issues across all categories."""
    return sum(len(v) for v in result.values() if isinstance(v, list))


def run_llm_judge_multi_pass(
    vendor_name: str,
    gaps: list[dict],
    recommendations: list[dict],
    remedial_actions: list[dict],
    all_questions: list[dict],
    artifacts: list[dict],
    overall_risk_rating: str,
    llm_fn,
    iterations: int = JUDGE_ITERATIONS,
) -> tuple[list[dict], list[dict], list[dict], dict, list[str]]:
    """
    Run the judge for `iterations` passes, applying corrections after each.

    Returns:
        (final_gaps, final_recommendations, final_remedial_actions,
         merged_judge_result, all_corrections_applied)
    """
    _severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    _empty = {
        "duplicate_gaps": [],
        "unsupported_gaps": [],
        "missing_controls": [],
        "severity_issues": [],
        "clause_issues": [],
        "recommendation_improvements": [],
        "summary_issues": [],
    }

    merged_result = {k: [] for k in _empty}
    all_corrections: list[str] = []
    pass_details: list[dict] = []

    for iteration in range(1, iterations + 1):
        logger.info(
            "[JUDGE] Pass %d/%d — reviewing %d gaps, %d recommendations, %d actions",
            iteration, iterations, len(gaps), len(recommendations), len(remedial_actions),
        )

        result = run_llm_judge(
            vendor_name=vendor_name,
            gaps=gaps,
            recommendations=recommendations,
            remedial_actions=remedial_actions,
            all_questions=all_questions,
            artifacts=artifacts,
            overall_risk_rating=overall_risk_rating,
            llm_fn=llm_fn,
        )

        issue_count = _count_issues(result)
        logger.info("[JUDGE] Pass %d found %d issue(s)", iteration, issue_count)

        # Merge into cumulative result
        merged_result = _merge_judge_results(merged_result, result)

        # Apply corrections immediately so next pass reviews the improved output
        if issue_count > 0:
            gaps, recommendations, remedial_actions, corrections = apply_judge_corrections(
                gaps, recommendations, remedial_actions, result,
            )
            labelled = [f"[pass {iteration}] {c}" for c in corrections]
            all_corrections.extend(labelled)

            # Re-derive overall severity after corrections
            overall_risk_rating = "low"
            for g in gaps:
                if _severity_order.get(g.get("severity", "medium"), 1) > _severity_order.get(overall_risk_rating, 0):
                    overall_risk_rating = g["severity"]
        else:
            logger.info(
                "[JUDGE] Pass %d returned zero issues — assessment is stable. "
                "Skipping remaining passes.",
                iteration,
            )
            pass_details.append({"pass": iteration, "issues": 0, "early_stop": True})
            break

        pass_details.append({"pass": iteration, "issues": issue_count, "corrections": len(corrections)})

    logger.info(
        "[JUDGE] Multi-pass complete: %d iteration(s), %d total correction(s), "
        "final gap count: %d",
        len(pass_details), len(all_corrections), len(gaps),
    )
    merged_result["_pass_details"] = pass_details

    return gaps, recommendations, remedial_actions, merged_result, all_corrections


def apply_judge_corrections(
    gaps: list[dict],
    recommendations: list[dict],
    remedial_actions: list[dict],
    judge_result: dict,
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """
    Apply judge corrections to gaps, recommendations, and remedial actions.

    NON-DESTRUCTIVE — gaps are NEVER removed. The gap analysis dedup chain
    already handles duplicate/speculative gaps upstream. The judge only:
      1. Logs duplicate/unsupported findings as informational metadata
      2. Corrects severity labels
      3. Improves recommendation wording

    Returns (gaps, recommendations, remedial_actions, corrections_applied).
    """
    corrections_applied = []

    # ── 1. Log duplicate gaps (informational — NOT removed) ────────────────────
    duplicate_groups = judge_result.get("duplicate_gaps") or []
    dup_count = sum(max(0, len(g.get("gap_ids", [])) - 1) for g in duplicate_groups)
    if dup_count:
        corrections_applied.append(f"Flagged {dup_count} potential duplicate gap(s) (kept — informational only)")
        logger.info("Judge flagged %d potential duplicate gap(s) — kept as informational", dup_count)

    # ── 2. Log unsupported gaps (informational — NOT removed) ──────────────────
    unsupported = judge_result.get("unsupported_gaps") or []
    if unsupported:
        corrections_applied.append(f"Flagged {len(unsupported)} potentially unsupported gap(s) (kept — informational only)")
        logger.info("Judge flagged %d potentially unsupported gap(s) — kept as informational", len(unsupported))

    # ── 3. Fix severity labels ─────────────────────────────────────────────────
    severity_issues = judge_result.get("severity_issues") or []
    severity_map = {
        str(s.get("gap_id", s.get("gap_id", ""))): s.get("suggested_severity")
        for s in severity_issues
        if s.get("suggested_severity") in ("critical", "high", "medium", "low")
    }
    severity_fixed = 0
    for g in gaps:
        gid = str(g.get("id", g.get("gap_id", "")))
        if gid in severity_map:
            old = g.get("severity")
            g["severity"] = severity_map[gid]
            if old != g["severity"]:
                severity_fixed += 1
    if severity_fixed:
        corrections_applied.append(f"Corrected severity on {severity_fixed} gap(s)")
        logger.info("Judge corrected severity on %d gap(s)", severity_fixed)

    # ── 4. Apply recommendation wording improvements ─────────────────────────────
    rec_improvements = judge_result.get("recommendation_improvements") or []
    rec_map = {
        str(r.get("recommendation_id", r.get("id", ""))): r.get("improved_text", "")
        for r in rec_improvements
        if r.get("improved_text")
    }
    rec_improved = 0
    for rec in recommendations:
        rid = str(rec.get("id", rec.get("recommendation_id", "")))
        if rid in rec_map and rec_map[rid]:
            rec["justification"] = rec_map[rid]
            rec_improved += 1
    if rec_improved:
        corrections_applied.append(f"Improved wording on {rec_improved} recommendation(s)")
        logger.info("Judge improved wording on %d recommendation(s)", rec_improved)

    return gaps, recommendations, remedial_actions, corrections_applied
