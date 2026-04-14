"""
Remedial Plan Service
=====================
Generates one actionable remediation action per compliance gap.
Each action has a timeline, owner, and clear acceptance criteria.
"""
import json
import logging
import uuid

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

logger = logging.getLogger("tprm.remedial_plan")

_PRIORITY_ORDER = {"immediate": 0, "short_term": 1, "medium_term": 2, "long_term": 3}
_SEV_TO_PRIORITY = {
    "critical": "immediate",
    "high": "short_term",
    "medium": "medium_term",
    "low": "long_term",
}
_SEV_TO_TIMELINE = {
    "critical": "Within 30 days",
    "high": "Within 90 days",
    "medium": "Within 6 months",
    "low": "Within 12 months",
}


def run_remedial_plan(
    gaps: list[dict],
    vendor_name: str,
    llm_fn,
    render_prompt_fn,
    get_system_prompt_fn,
) -> list[dict]:
    """Generate one remediation action per eligible gap. Returns a sorted list of action dicts.

    Only gaps of type 'control_missing' or 'policy_violation' receive remediation actions.
    """
    REMEDIABLE_TYPES = {"control_missing", "policy_violation"}
    eligible_gaps = [g for g in gaps if g.get("gap_type") in REMEDIABLE_TYPES]
    if not eligible_gaps:
        return []

    gaps_data = json.dumps(
        [
            {
                "gap_id": g["id"],
                "gap_type": g["gap_type"],
                "severity": g["severity"],
                "description": g["description"],
                "evidence_assessment": g.get("evidence_assessment", ""),
            }
            for g in eligible_gaps
        ],
        indent=2,
    )

    prompt = render_prompt_fn("remedial_plan", gaps_data=gaps_data, vendor_name=vendor_name)
    system = get_system_prompt_fn("remedial_plan")

    try:
        result = llm_fn(prompt, system_prompt=system)
    except Exception as exc:
        logger.error("Remedial plan LLM call failed: %s", exc)
        return _fallback(eligible_gaps)

    raw = result.get("remedial_actions", [])
    if not isinstance(raw, list):
        logger.warning("Unexpected remedial_plan LLM structure; using fallback")
        return _fallback(eligible_gaps)

    gap_lookup = {g["id"]: g for g in eligible_gaps}
    seen = set()
    actions = []

    for item in raw:
        gap_id = item.get("gap_id", "")
        if not gap_id or gap_id not in gap_lookup or gap_id in seen:
            continue
        seen.add(gap_id)
        action_text = (item.get("action") or "").strip()
        actions.append(
            {
                "id": str(uuid.uuid5(_NS, f"remedial:{gap_id}:{action_text[:200]}")),
                "gap_id": gap_id,
                "action": action_text,
                "priority": item.get("priority", "medium_term"),
                "timeline": (item.get("timeline") or "Within 90 days").strip(),
                "owner": (item.get("owner") or "Vendor Security Team").strip(),
                "acceptance_criteria": (item.get("acceptance_criteria") or "").strip(),
            }
        )

    # Ensure every eligible gap has an action (fallback for any LLM missed)
    for g in eligible_gaps:
        if g["id"] not in seen:
            actions.append(_default_action(g))

    # Sort by priority: immediate → short_term → medium_term → long_term, then gap_id
    actions.sort(key=lambda a: (_PRIORITY_ORDER.get(a["priority"], 2), a.get("gap_id", "")))
    return actions


def _default_action(gap: dict) -> dict:
    sev = gap.get("severity", "medium")
    return {
        "id": str(uuid.uuid5(_NS, f"remedial:{gap['id']}:fallback")),
        "gap_id": gap["id"],
        "action": f"Remediate gap: {gap.get('description', '')[:200]}",
        "priority": _SEV_TO_PRIORITY.get(sev, "medium_term"),
        "timeline": _SEV_TO_TIMELINE.get(sev, "Within 6 months"),
        "owner": "Vendor Security Team",
        "acceptance_criteria": "Provide documented evidence of remediation completion",
    }


def _fallback(gaps: list[dict]) -> list[dict]:
    return [_default_action(g) for g in gaps]
