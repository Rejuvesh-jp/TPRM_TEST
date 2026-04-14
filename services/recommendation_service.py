"""
Recommendation Service
======================
Generates contract clause recommendations to mitigate identified risks.
Uses RAG to find existing contract clauses and suggests additions.
"""

import json
import logging
import uuid

from services.embedding_service import similarity_search

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

logger = logging.getLogger("tprm.recommendation")


def run_recommendations(gaps: list[dict], clauses: list[dict],
                        embed_fn, llm_fn, render_prompt_fn, get_system_prompt_fn) -> list[dict]:
    """
    Generate clause recommendations:
      1. Build gaps context for LLM
      2. RAG: retrieve relevant existing contract clauses per gap
      3. Pass ALL unique matched clauses to LLM
      4. LLM: identify applicable existing clauses and suggest new ones

    Returns list of recommendation dicts.
    """
    gaps_data = json.dumps([
        {
            "gap_id": g["id"],
            "gap_type": g["gap_type"],
            "severity": g["severity"],
            "description": g["description"],
            "evidence_assessment": g.get("evidence_assessment", ""),
        }
        for g in gaps
    ], indent=2)

    gap_id_set = {g["id"] for g in gaps}

    # RAG: search clauses per gap to get comprehensive coverage
    seen_clause_ids = set()
    matched_clauses = []

    for g in gaps:
        query = g.get("description", "") or g.get("gap_type", "security compliance")
        if not query.strip():
            continue
        query_emb = embed_fn(query)
        results = similarity_search(query_emb, clauses, top_k=5) if clauses else []
        for sim, c in results:
            if c["id"] not in seen_clause_ids:
                seen_clause_ids.add(c["id"])
                matched_clauses.append({
                    "id": c["id"],
                    "category": c.get("category", ""),
                    "content": c["content"][:3000],
                })

    # RAG: also search clauses for FUTURE risk topics so the LLM has
    # relevant existing clauses available when generating future-risk recs
    future_risk_queries = [
        "AI governance artificial intelligence machine learning",
        "supply chain third party subcontractor risk",
        "data sovereignty cross-border data transfer jurisdiction",
        "technology obsolescence end of life migration modernization",
        "vendor lock-in exit transition portability",
        "regulatory compliance emerging regulations",
        "cyber insurance liability indemnification",
        "business continuity disaster recovery force majeure",
        "workforce changes personnel key person dependency",
        "intellectual property rights ownership",
    ]
    for fq in future_risk_queries:
        if not clauses:
            break
        fq_emb = embed_fn(fq)
        results = similarity_search(fq_emb, clauses, top_k=3)
        for sim, c in results:
            if c["id"] not in seen_clause_ids:
                seen_clause_ids.add(c["id"])
                matched_clauses.append({
                    "id": c["id"],
                    "category": c.get("category", ""),
                    "content": c["content"][:3000],
                })

    # Also add all clauses if total is manageable (< 50)
    if len(clauses) <= 50:
        for c in clauses:
            if c["id"] not in seen_clause_ids:
                seen_clause_ids.add(c["id"])
                matched_clauses.append({
                    "id": c["id"],
                    "category": c.get("category", ""),
                    "content": c["content"][:3000],
                })

    existing_clauses = json.dumps(matched_clauses, indent=2)
    logger.info("Sending %d existing clauses to LLM for recommendation analysis", len(matched_clauses))

    rec_prompt = render_prompt_fn("recommendation", **{
        "gaps_data": gaps_data,
        "existing_clauses": existing_clauses,
    })
    rec_system = get_system_prompt_fn("recommendation")
    rec_result = llm_fn(rec_prompt, system_prompt=rec_system)

    recommendations = []
    for rec_data in rec_result.get("recommendations", []):
        gap_id_str = rec_data.get("gap_id", "")
        source = rec_data.get("source", "new")

        # Future risk clauses don't map to a specific gap
        # Only keep future-risk recs that reference an existing clause
        if gap_id_str == "FUTURE" or source == "future_risk":
            if source != "existing":
                continue  # skip new/drafted future-risk clauses
            clause_txt = rec_data.get("recommended_clause", "")
            recommendations.append({
                "id": str(uuid.uuid5(_NS, f"rec:FUTURE:{clause_txt[:200]}")),
                "gap_id": "FUTURE",
                "clause_text": clause_txt,
                "justification": rec_data.get("justification", ""),
                "existing_coverage": rec_data.get("existing_coverage", "none"),
                "priority": rec_data.get("priority", "should_have"),
                "source": "existing",
                "source_clause_id": rec_data.get("source_clause_id"),
            })
            continue

        if gap_id_str not in gap_id_set:
            continue
        clause_text = rec_data.get("recommended_clause", "")
        recommendations.append({
            "id": str(uuid.uuid5(_NS, f"rec:{gap_id_str}:{clause_text[:200]}")),
            "gap_id": gap_id_str,
            "clause_text": rec_data.get("recommended_clause", ""),
            "justification": rec_data.get("justification", ""),
            "existing_coverage": rec_data.get("existing_coverage"),
            "priority": rec_data.get("priority"),
            "source": source,
            "source_clause_id": rec_data.get("source_clause_id"),
        })

    # Sort deterministically: existing clauses first, then by gap_id, then clause text
    _src_order = {"existing": 0, "future_risk": 1, "new": 2}
    recommendations.sort(key=lambda r: (
        _src_order.get(r.get("source", "new"), 2),
        r.get("gap_id", ""),
        r.get("clause_text", ""),
    ))

    # Deduplicate by clause text — if the same clause is recommended for multiple
    # gaps, keep a single entry and merge the gap_ids into a list.
    import re as _re
    _seen_clauses: dict[str, dict] = {}  # normalized_text -> recommendation dict
    deduped_recs: list[dict] = []
    for rec in recommendations:
        norm = _re.sub(r'\s+', ' ', (rec.get("clause_text") or "").strip().lower())
        if not norm:
            deduped_recs.append(rec)
            continue
        if norm in _seen_clauses:
            # Merge gap_id into existing entry's gap_ids list
            existing = _seen_clauses[norm]
            if "gap_ids" not in existing:
                existing["gap_ids"] = [existing["gap_id"]]
            new_gid = rec.get("gap_id", "")
            if new_gid and new_gid not in existing["gap_ids"]:
                existing["gap_ids"].append(new_gid)
            # Keep higher priority
            _pri_order = {"must_have": 0, "should_have": 1, "nice_to_have": 2}
            if _pri_order.get(rec.get("priority"), 2) < _pri_order.get(existing.get("priority"), 2):
                existing["priority"] = rec["priority"]
        else:
            _seen_clauses[norm] = rec
            deduped_recs.append(rec)

    if len(recommendations) != len(deduped_recs):
        logger.info("Recommendation dedup: %d → %d (merged %d duplicate clauses)",
                     len(recommendations), len(deduped_recs),
                     len(recommendations) - len(deduped_recs))
    recommendations = deduped_recs

    return recommendations
