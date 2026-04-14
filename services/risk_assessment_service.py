"""
Risk Assessment Service
=======================
Scores compliance gaps by severity, regulatory impact, and vendor maturity.
"""

import json
import logging
import uuid

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

logger = logging.getLogger("tprm.risk_assessment")


def run_risk_assessment(gaps: list[dict], vendor_name: str,
                        llm_fn, render_prompt_fn, get_system_prompt_fn) -> dict:
    """
    Score gaps:
      1. Build gaps data for LLM prompt
      2. LLM assigns risk levels, rationale, remediation plans
      3. Compute overall risk rating

    Returns dict with risks, overall_risk_rating, executive_summary.
    """
    gaps_data = json.dumps([
        {
            "gap_id": g["id"],
            "gap_type": g["gap_type"],
            "description": g["description"],
            "severity": g["severity"],
            "source_refs": g["source_refs"],
        }
        for g in gaps
    ], indent=2)

    vendor_context = json.dumps({
        "vendor_name": vendor_name,
    })

    risk_prompt = render_prompt_fn("risk_assessment", **{
        "gaps_data": gaps_data,
        "vendor_context": vendor_context,
    })
    risk_system = get_system_prompt_fn("risk_assessment")
    risk_result = llm_fn(risk_prompt, system_prompt=risk_system)

    gap_id_set = {g["id"] for g in gaps}
    risks = []
    for score in risk_result.get("risk_scores", []):
        gid = score.get("gap_id", "")
        if gid not in gap_id_set:
            continue
        risks.append({
            "id": str(uuid.uuid5(_NS, f"risk:{gid}")),
            "gap_id": gid,
            "risk_level": score.get("risk_level", "medium"),
            "rationale": score.get("rationale", ""),
            "remediation_plan": score.get("remediation_plan"),
            "regulatory_impact": score.get("regulatory_impact"),
            "priority": score.get("priority"),
        })

    return {
        "risks": risks,
        "overall_risk_rating": risk_result.get("overall_risk_rating", "N/A"),
        "executive_summary": risk_result.get("executive_summary", ""),
    }
