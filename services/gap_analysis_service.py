"""
Gap Analysis Service
====================
Cross-references questionnaire responses against artifact evidence,
policy requirements, and contract clauses to identify compliance gaps.
"""

import json
import logging
import re
import uuid

from services.embedding_service import similarity_search

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')
from services.questionnaire_parser import INFO_ONLY_SECTIONS

logger = logging.getLogger("tprm.gap_analysis")


def run_gap_analysis(questions: list[dict], artifacts: list[dict],
                     policies: list[dict], clauses: list[dict],
                     embed_fn, llm_fn, render_prompt_fn, get_system_prompt_fn,
                     reference_gaps: list[dict] | None = None) -> dict:
    """
    Perform gap analysis:
      1. RAG: search artifact chunks for evidence matching security questions
      2. RAG: search policies for compliance context
      3. RAG: search contract clauses for obligation context
      4. LLM: identify gaps from all evidence

    Returns dict with gaps, evidence stats, and coverage summary.
    """
    # Collect all artifact chunks
    all_chunks = []
    for art in artifacts:
        all_chunks.extend(art.get("chunks", []))

    # RAG: search artifact chunks for security-domain questions
    logger.info("Running RAG search: questions vs artifact chunks")
    artifact_evidence_items = []
    searched_questions = 0

    for q in questions:
        if q.get("section") in INFO_ONLY_SECTIONS:
            continue
        searched_questions += 1
        query_text = f"{q['section']}: {q['question_text']}"
        if q.get("response_text"):
            query_text += f" | Response: {q['response_text'][:200]}"
        query_emb = q.get("question_embedding") or embed_fn(query_text)
        results = similarity_search(query_emb, all_chunks, top_k=5)
        for sim, chunk in results:
            artifact_evidence_items.append({
                "id": chunk["id"],
                "content": chunk["content"],
                "metadata": chunk["metadata"],
                "distance": round(1 - sim, 6),
                "matched_question": q["control_id"],
            })

    logger.info("Searched %d security-domain questions against %d chunks",
                searched_questions, len(all_chunks))

    # Deduplicate evidence
    seen = set()
    unique_evidence = []
    for item in artifact_evidence_items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique_evidence.append(item)

    # Stable sort: by distance (ascending = most similar first), then chunk ID as tiebreaker.
    # This ensures identical evidence order in the prompt regardless of question processing order.
    unique_evidence.sort(key=lambda x: (round(x["distance"], 4), x["id"]))
    unique_evidence = unique_evidence[:200]

    logger.debug(
        "Evidence order (top 10): %s",
        [(e["id"][:12], e["distance"]) for e in unique_evidence[:10]],
    )
    artifact_evidence = json.dumps(unique_evidence, indent=2)
    logger.info("%d unique evidence chunks (from %d total matches)",
                len(unique_evidence), len(artifact_evidence_items))

    # RAG: search policies
    policy_query_emb = embed_fn("security compliance controls")
    policy_chunks = []
    for p in policies:
        for c in p.get("chunks", []):
            c["title"] = p["title"]
            policy_chunks.append(c)
    policy_results = similarity_search(policy_query_emb, policy_chunks, top_k=10) if policy_chunks else []
    logger.debug(
        "Policy chunk order: %s",
        [(r["id"][:12], round(1 - sim, 4)) for sim, r in policy_results],
    )
    policy_context = json.dumps([
        {"id": r["id"], "title": r.get("title", ""), "content": r["content"][:2000],
         "distance": round(1 - sim, 6)}
        for sim, r in policy_results
    ], indent=2)

    # RAG: search contract clauses
    clause_query_emb = embed_fn("vendor obligations security data protection")
    clause_results = similarity_search(clause_query_emb, clauses, top_k=5) if clauses else []
    logger.debug(
        "Clause order: %s",
        [(r["id"][:12], round(1 - sim, 4)) for sim, r in clause_results],
    )
    contract_context = json.dumps([
        {"id": r["id"], "category": r["category"], "content": r["content"][:2000],
         "distance": round(1 - sim, 6)}
        for sim, r in clause_results
    ], indent=2)

    # Build artifact insight summaries so the LLM knows what the artifacts prove
    artifact_insight_summary = json.dumps([
        {
            "file_name": art["file_name"],
            "source_type": art.get("source_type", "document"),
            "insights": art.get("insights", {}),
        }
        for art in artifacts
        if art.get("insights")
    ], indent=2)
    logger.info("Passing %d artifact insight summaries to gap analysis",
                sum(1 for a in artifacts if a.get("insights")))

    # Build list of valid control IDs so the LLM can reference them
    _all_control_ids = sorted(set(
        q["control_id"] for q in questions if q.get("control_id")
    ))

    # Detect truly unanswered questions (no response at all).
    # "Not applicable" / "N/A" are NOT auto-flagged — the LLM evaluates whether
    # N/A is reasonable given the vendor context and available artifacts.
    _UNANSWERED_PATTERNS = frozenset({
        "not answered", "none", "-", "",
        "no response", "no answer", "not provided", "not available",
    })
    # "Not applicable" patterns — sent to LLM for evaluation, not auto-flagged
    _NA_PATTERNS = frozenset({"not applicable", "n/a", "na"})

    def _is_unanswered(q: dict) -> bool:
        """True if the question has NO vendor response (not even N/A)."""
        rt = (q.get("response_text") or "").strip().lower()
        return not rt or rt in _UNANSWERED_PATTERNS

    def _is_not_applicable(q: dict) -> bool:
        """True if the vendor marked the question as Not Applicable."""
        rt = (q.get("response_text") or "").strip().lower()
        return rt in _NA_PATTERNS

    _unanswered_ids = sorted(set(
        q["control_id"] for q in questions
        if q.get("control_id") and _is_unanswered(q)
        and q.get("section") not in INFO_ONLY_SECTIONS
    ))

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1: Deterministic gaps for UNANSWERED security questions
    # ══════════════════════════════════════════════════════════════════════════
    # These are 100% consistent across runs — same input always = same gaps.
    _unanswered_qid_set = set(_unanswered_ids)
    deterministic_gaps: list[dict] = []
    _q_lookup = {q["control_id"]: q for q in questions if q.get("control_id")}

    for qid in _unanswered_ids:
        q = _q_lookup.get(qid)
        if not q:
            continue
        raw_resp = (q.get("response_text") or "").strip()
        raw_resp_lower = raw_resp.lower()

        # Tailor description based on what the vendor actually put
        if raw_resp_lower in ("not applicable", "n/a", "na"):
            desc = (
                f"Vendor marked as 'Not Applicable': {q.get('question_text', qid)}. "
                "No justification was provided for why this control is not applicable — "
                "treated as control not confirmed."
            )
            evidence = (
                f"Vendor response: '{raw_resp}'. No supporting justification or "
                "compensating control was documented."
            )
        elif raw_resp_lower == "not answered" or not raw_resp:
            desc = (
                f"No response was provided for: {q.get('question_text', qid)}. "
                "Vendor did not answer this security control question — treated as control not confirmed."
            )
            evidence = (
                "Vendor did not provide any response to this question. "
                "No evidence available to confirm the control is in place."
            )
        else:
            desc = (
                f"Non-substantive response for: {q.get('question_text', qid)}. "
                f"Vendor response: '{raw_resp}' — insufficient to confirm control."
            )
            evidence = (
                f"Vendor response '{raw_resp}' is not a substantive answer. "
                "No evidence available to confirm the control is in place."
            )

        deterministic_gaps.append({
            "id": str(uuid.uuid5(_NS, f"gap:control_missing:{qid}:unanswered")),
            "gap_type": "control_missing",
            "description": desc,
            "severity": "medium",
            "confidence": 95,
            "related_question_id": qid,
            "source_refs": {"questionnaire": [f"{qid} — {raw_resp or 'no response provided'}"]},
            "evidence_assessment": evidence,
        })

    logger.info(
        "[DETERMINISTIC] Generated %d control_missing gaps for unanswered questions",
        len(deterministic_gaps),
    )

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2: LLM gap analysis for ANSWERED questions only
    # ══════════════════════════════════════════════════════════════════════════
    # The LLM evaluates evidence quality for questions the vendor DID answer.
    # It finds: unsupported_claim, policy_violation, missing_artifact gaps.
    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2: LLM gap analysis for ANSWERED questions only
    # ══════════════════════════════════════════════════════════════════════════
    # The LLM evaluates evidence quality for questions the vendor DID answer.
    # It finds: unsupported_claim, policy_violation, missing_artifact gaps.
    #
    # SECTION BATCHING: Instead of sending ALL questions in one giant prompt
    # (which causes the LLM to skip/rush later sections), we split questions
    # into smaller batches grouped by section.  Each batch gets a focused LLM
    # call with full evidence, so every section receives proper attention.
    # ══════════════════════════════════════════════════════════════════════════

    # Collect answered + N/A questions (truly unanswered handled in Phase 1)
    _answered_questions = [
        q for q in questions
        if not _is_unanswered(q) and q.get("section") not in INFO_ONLY_SECTIONS
    ]

    # Group by section, preserving order
    from collections import OrderedDict
    _section_groups: dict[str, list[dict]] = OrderedDict()
    for q in _answered_questions:
        sec = q.get("section", "Unknown")
        _section_groups.setdefault(sec, []).append(q)

    # Build batches: merge small sections so each batch has ~20-30 questions
    _BATCH_TARGET = 25
    _batches: list[tuple[list[str], list[dict]]] = []
    _cur_batch_qs: list[dict] = []
    _cur_batch_secs: list[str] = []
    for sec, sec_qs in _section_groups.items():
        if _cur_batch_qs and len(_cur_batch_qs) + len(sec_qs) > _BATCH_TARGET:
            _batches.append((_cur_batch_secs[:], _cur_batch_qs[:]))
            _cur_batch_qs = []
            _cur_batch_secs = []
        _cur_batch_qs.extend(sec_qs)
        _cur_batch_secs.append(sec)
    if _cur_batch_qs:
        _batches.append((_cur_batch_secs[:], _cur_batch_qs[:]))

    logger.info(
        "[BATCH] Split %d answered questions across %d sections into %d batches: %s",
        len(_answered_questions), len(_section_groups), len(_batches),
        [(secs, len(qs)) for secs, qs in _batches],
    )

    # ── Build reference gaps from previous assessment ────────────────────────
    _ref_llm_gaps = []
    if reference_gaps:
        _ref_llm_gaps = [
            {
                "gap_type": g.get("gap_type"),
                "description": g.get("description"),
                "severity": g.get("severity"),
                "related_question_id": g.get("related_question_id"),
            }
            for g in reference_gaps
            if g.get("gap_type") != "control_missing"
        ]

    gap_system = get_system_prompt_fn("gap_analysis")

    # ── Run LLM for each batch ───────────────────────────────────────────────
    all_raw_gaps: list[dict] = []
    import hashlib as _hl

    for _batch_idx, (_batch_secs, _batch_qs) in enumerate(_batches, 1):
        _batch_insights = json.dumps([
            {
                "control_id": q["control_id"],
                "section": q["section"],
                "question": q["question_text"],
                "response": q["response_text"],
                "justification": q["justification"],
                "risk_relevance": q["risk_relevance"],
                "claim_strength": q["claim_strength"],
                "flags": q["flags"],
            }
            for q in _batch_qs
        ], indent=2)

        _batch_cids = sorted(set(q["control_id"] for q in _batch_qs))

        gap_prompt = render_prompt_fn("gap_analysis", **{
            "questionnaire_insights": _batch_insights,
            "artifact_evidence": artifact_evidence,
            "artifact_insight_summary": artifact_insight_summary,
            "policy_context": policy_context,
            "contract_context": contract_context,
        })

        # Append batch-specific control IDs and unanswered exclusions
        gap_prompt += (
            "\n\n--- VALID CONTROL IDS FOR THIS BATCH (evaluate ALL of them) ---\n"
            + json.dumps(_batch_cids)
            + "\n\nYou MUST evaluate every single question listed above. There are "
            + str(len(_batch_qs)) + " questions in this batch across sections: "
            + ", ".join(_batch_secs) + ". Do NOT skip any."
            + "\n\n--- ALREADY HANDLED (DO NOT flag these — they are automatically flagged) ---\n"
            "The following " + str(len(_unanswered_ids)) + " unanswered questions are ALREADY "
            "flagged as control_missing gaps by the system. DO NOT include them in your output:\n"
            + json.dumps(_unanswered_ids)
        )

        # Reference gaps for this batch
        if _ref_llm_gaps:
            _batch_ref = [
                g for g in _ref_llm_gaps
                if g.get("related_question_id") in set(_batch_cids)
            ]
            if _batch_ref:
                gap_prompt += (
                    "\n\n--- REFERENCE: GAPS FROM PREVIOUS ASSESSMENT OF THIS VENDOR ---\n"
                    "A previous assessment of the same vendor identified the following "
                    "evidence-based gaps for questions in THIS batch. Use as reference:\n"
                    "- If the evidence STILL supports a reference gap, include it "
                    "(you may refine the wording).\n"
                    "- If new evidence now contradicts a reference gap, do NOT include it.\n"
                    "- If you find NEW gaps not in the reference, include them.\n"
                    "- Do NOT blindly copy — re-evaluate against actual evidence.\n\n"
                    + json.dumps(_batch_ref, indent=2)
                )

        # Log prompt fingerprint per batch
        _prompt_hash = _hl.sha256((gap_system + gap_prompt).encode()).hexdigest()[:16]
        logger.info(
            "[BATCH %d/%d] Sections: %s | Questions: %d | Prompt FP: %s (len=%d)",
            _batch_idx, len(_batches), _batch_secs, len(_batch_qs),
            _prompt_hash, len(gap_prompt),
        )

        batch_result = llm_fn(gap_prompt, system_prompt=gap_system)
        batch_gaps = batch_result.get("gaps", [])
        logger.info("[BATCH %d/%d] Raw gaps returned: %d", _batch_idx, len(_batches), len(batch_gaps))

        all_raw_gaps.extend(batch_gaps)

    if _ref_llm_gaps:
        logger.info("[REFERENCE] Total reference gaps used: %d", len(_ref_llm_gaps))
    else:
        logger.info("[REFERENCE] No reference gaps available (first assessment or no prior LLM gaps)")

    logger.info("TOTAL raw gaps from all %d batches: %d", len(_batches), len(all_raw_gaps))

    # Build gap entries
    _severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    raw_gaps = all_raw_gaps
    logger.info("RAW gap count from LLM: %d", len(raw_gaps))

    # ── Normalize raw gap fields before any dedup ─────────────────────────────
    _GAP_TYPE_ALIASES = {
        # canonicalize free-text variants the LLM sometimes produces
        "missing_control":      "control_missing",
        "control missing":      "control_missing",
        "control gap":          "control_missing",
        "missing control":      "control_missing",
        "policy_gap":           "policy_gap",
        "policy gap":           "policy_gap",
        "policy missing":       "policy_gap",
        "process_gap":          "process_gap",
        "process gap":          "process_gap",
        "evidence_gap":         "evidence_gap",
        "evidence gap":         "evidence_gap",
        "lack of evidence":     "evidence_gap",
        "insufficient_evidence":"evidence_gap",
        "data_protection_gap":  "data_protection_gap",
        "data protection gap":  "data_protection_gap",
        "third_party_risk":     "third_party_risk",
        "third party risk":     "third_party_risk",
    }

    def _normalize_gap_type(gt: str) -> str:
        gt_l = gt.strip().lower().replace("-", "_")
        return _GAP_TYPE_ALIASES.get(gt_l, gt_l)

    def _normalize_qid(qid: str) -> str:
        """Strip leading zeros, extra spaces, dots — e.g. 'Q01' == 'Q1', 'AM-01' == 'AM-1'."""
        import re as _re
        if not qid:
            return ""
        qid = qid.strip().upper()
        # Normalize numeric suffix: AM-01 → AM-1, GV.1.01 → GV.1.1
        qid = _re.sub(r"(?<=[.\-])0+(\d)", r"\1", qid)
        return qid

    def _desc_key(desc: str) -> str:
        """Collapse whitespace and lowercase for comparison."""
        import re as _re
        return _re.sub(r"\s+", " ", desc.strip().lower())[:120]

    normalized_raw = []
    _llm_control_missing_dropped = 0
    for gd in raw_gaps:
        gt = _normalize_gap_type(gd.get("gap_type", "unknown"))
        qid = _normalize_qid(gd.get("related_question_id") or "")
        desc = gd.get("description", "").strip()
        sev = gd.get("severity", "medium").strip().lower()
        if sev not in _severity_rank:
            sev = "medium"
        # Drop control_missing from LLM only if it's for a truly unanswered question
        # (those are already handled deterministically in Phase 1).
        # Allow control_missing for N/A questions — the LLM evaluates if N/A is valid.
        if gt == "control_missing" and qid in _unanswered_qid_set:
            _llm_control_missing_dropped += 1
            logger.debug("Dropped LLM control_missing for deterministic Q: %s", qid)
            continue
        normalized_raw.append({**gd, "gap_type": gt, "related_question_id": qid or None,
                                "severity": sev, "description": desc})

    if _llm_control_missing_dropped:
        logger.info(
            "[FILTER] Dropped %d control_missing gaps from LLM (handled deterministically)",
            _llm_control_missing_dropped,
        )

    # ── Auto-map gaps to question IDs if the LLM didn't fill them ────────────
    # The LLM frequently omits related_question_id even though its description
    # clearly references a specific control.  Two strategies:
    #   1. Regex: scan desc + evidence + source_refs for control ID patterns
    #   2. Semantic: embed-match the gap description to the closest question
    _valid_cid_set = set(_all_control_ids)

    def _extract_qid_from_text(text: str) -> str | None:
        """Try to extract a valid control ID from free text using regex."""
        if not text:
            return None
        # Match patterns like A.5, DRL.5, BI.20, PBA.3, H.1.2, etc.
        import re as _re
        candidates = _re.findall(r'\b([A-Z]{1,4})[.\-](\d+(?:\.\d+)?)\b', text.upper())
        for prefix, num in candidates:
            cid = f"{prefix}.{num}"
            cid = _normalize_qid(cid)
            if cid in _valid_cid_set:
                return cid
        return None

    # Build question text lookup for semantic matching
    _q_text_map: dict[str, str] = {}
    _q_embed_map: dict[str, list] = {}
    for q in questions:
        cid = q.get("control_id", "")
        if cid and q.get("section") not in INFO_ONLY_SECTIONS:
            _q_text_map[cid] = (q.get("question_text") or "").lower()
            if q.get("question_embedding"):
                _q_embed_map[cid] = q["question_embedding"]

    def _semantic_match_qid(desc: str) -> str | None:
        """Match gap description to closest question by embedding similarity."""
        if not _q_embed_map or not desc.strip():
            return None
        try:
            gap_emb = embed_fn(desc[:500])
            import numpy as _np
            best_cid, best_sim = None, -1.0
            for cid, q_emb in _q_embed_map.items():
                g = _np.array(gap_emb, dtype=_np.float32)
                q = _np.array(q_emb, dtype=_np.float32)
                g_norm = _np.linalg.norm(g)
                q_norm = _np.linalg.norm(q)
                if g_norm == 0 or q_norm == 0:
                    continue
                sim = float(_np.dot(g, q) / (g_norm * q_norm))
                if sim > best_sim:
                    best_sim = sim
                    best_cid = cid
            if best_sim >= 0.50 and best_cid:
                return best_cid
        except Exception:
            pass
        return None

    mapped_count = 0
    for gd in normalized_raw:
        if gd.get("related_question_id"):
            continue  # already has a QID
        # Strategy 1: regex extraction from all text fields
        all_text = " ".join(filter(None, [
            gd.get("description", ""),
            gd.get("evidence_assessment", ""),
            json.dumps(gd.get("source_refs") or {}),
        ]))
        qid = _extract_qid_from_text(all_text)
        if qid:
            gd["related_question_id"] = qid
            mapped_count += 1
            continue
        # Strategy 2: semantic match to closest question
        qid = _semantic_match_qid(gd.get("description", ""))
        if qid:
            gd["related_question_id"] = qid
            mapped_count += 1

    if mapped_count:
        logger.info("[QID-MAP] Auto-mapped %d gap(s) to question IDs", mapped_count)

    # NOTE: Confidence score is kept as metadata on each gap (for the judge to
    # reference) but we do NOT hard-filter by it.  Hard-filtering at a threshold
    # created a "flickering zone" where gaps scoring ±2 around the cutoff
    # appeared in one version but not the other — the opposite of consistency.
    # Instead, the 3-pass LLM judge will review and remove genuinely speculative
    # gaps via the "unsupported_gaps" category.

    # ── Deduplicate by normalized_qid ONLY (max 1 gap per question) ────────────
    # The LLM often assigns different gap_types to the same question across runs
    # (e.g. V1: "control_missing" vs V2: "unsupported_claim" for question A.5).
    # Keying by (qid, gap_type) lets both survive — causing gap count variance.
    # Fix: strictly 1 gap per question ID.  Keep higher severity; on tie keep
    # the one with a longer (more informative) description.
    #
    # Gaps WITHOUT a question_id are keyed by (gap_type, desc_prefix) instead.
    seen_keys: dict[str | tuple, dict] = {}
    for gd in normalized_raw:
        qid = _normalize_qid(gd.get("related_question_id") or "")
        sev = gd.get("severity", "medium")

        if qid:
            key: str | tuple = qid  # strict: 1 gap per question ID
        else:
            # Anonymous gap — key by (gap_type, first 80 chars of description)
            key = (gd.get("gap_type", "unknown"), _desc_key(gd.get("description", ""))[:80])

        existing = seen_keys.get(key)
        if existing is None:
            seen_keys[key] = gd
        else:
            ex_sev = existing.get("severity", "medium")
            if _severity_rank.get(sev, 2) < _severity_rank.get(ex_sev, 2):
                seen_keys[key] = gd  # higher severity wins
            elif _severity_rank.get(sev, 2) == _severity_rank.get(ex_sev, 2):
                if len(gd.get("description", "")) > len(existing.get("description", "")):
                    seen_keys[key] = gd  # same severity: keep longer description

    deduped = list(seen_keys.values())
    logger.info("Primary dedup: %d raw → %d gaps (max 1 per question ID)", len(normalized_raw), len(deduped))

    # ── Secondary dedup: collapse anonymous gaps with overlapping descriptions ─
    # Gaps with a question_id are already strictly 1-per-qid from primary dedup.
    # This pass targets anonymous gaps (no qid) that describe the same issue.
    final_deduped: list[dict] = []
    seen_secondary: set[str] = set()
    for gd in deduped:
        qid = _normalize_qid(gd.get("related_question_id") or "")
        if qid:
            # Has question ID — already deduped, pass through
            final_deduped.append(gd)
            continue
        # Anonymous gap — dedup by description prefix
        dk = _desc_key(gd.get("description", ""))[:100]
        if dk in seen_secondary:
            logger.debug("Secondary dedup removed anonymous gap: %s", dk[:60])
            continue
        seen_secondary.add(dk)
        final_deduped.append(gd)

    removed_duplicates = len(raw_gaps) - len(final_deduped)
    logger.info("Gap dedup: %d raw → %d after type-dedup → %d after desc-dedup (%d duplicates removed)",
                len(raw_gaps), len(deduped), len(final_deduped), removed_duplicates)

    # ── Word-set semantic dedup: catch near-duplicate descriptions ────────────
    # The LLM sometimes generates the same logical gap with slightly different
    # wording across runs. This collapses gaps whose word-sets overlap > 75%.
    _STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "must", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between", "out", "off",
        "over", "under", "again", "further", "then", "once", "and", "but", "or",
        "nor", "not", "no", "so", "if", "that", "than", "this", "these", "those",
        "it", "its", "they", "them", "their", "we", "our", "you", "your", "he",
        "she", "him", "her", "his", "any", "all", "each", "every", "both",
    })

    def _desc_words(desc: str) -> set[str]:
        """Extract meaningful content words from a description, with lightweight stemming."""
        import re as _re
        words = set(_re.findall(r"[a-z0-9]+", desc.strip().lower()))
        words -= _STOP_WORDS
        # Lightweight suffix stripping — order matters: try longer suffixes first.
        # Normalizes "encryption"→"encrypt", "provided"→"provid", "documents"→"document"→"doc"
        stemmed = set()
        _SUFFIXES = (
            "ation", "tion", "sion", "ment", "ness", "ence", "ance",
            "ity", "ing", "ied", "ies", "ers", "ors",
            "ed", "es", "ly", "er", "or", "al", "ous",
            "ive", "age", "ure", "s",
        )
        for w in words:
            for suffix in _SUFFIXES:
                if len(w) > len(suffix) + 3 and w.endswith(suffix):
                    w = w[:-len(suffix)]
                    break
            stemmed.add(w)
        return stemmed

    def _word_similarity(a: set[str], b: set[str]) -> float:
        """Overlap coefficient: shared words / smaller set — more lenient than Jaccard
        for descriptions of the same concept with different framing."""
        if not a or not b:
            return 0.0
        return len(a & b) / min(len(a), len(b))

    _SEMANTIC_SIM_THRESHOLD = 0.85
    semantic_deduped: list[dict] = []
    _existing_word_sets: list[tuple[set[str], dict]] = []  # (words, gap_dict)

    for gd in final_deduped:
        desc_ws = _desc_words(gd.get("description", ""))
        gd_qid = _normalize_qid(gd.get("related_question_id") or "")
        is_dup = False
        for existing_ws, existing_gd in _existing_word_sets:
            # NEVER merge gaps that belong to different questions — those are
            # genuinely distinct compliance findings even if similarly worded.
            ex_qid = _normalize_qid(existing_gd.get("related_question_id") or "")
            if gd_qid and ex_qid and gd_qid != ex_qid:
                continue
            sim = _word_similarity(desc_ws, existing_ws)
            if sim >= _SEMANTIC_SIM_THRESHOLD:
                # Same logical gap — keep the higher severity, or longer description
                e_sev = _severity_rank.get(existing_gd.get("severity", "medium"), 2)
                n_sev = _severity_rank.get(gd.get("severity", "medium"), 2)
                if n_sev < e_sev:
                    # New one has higher severity — replace
                    _existing_word_sets.remove((existing_ws, existing_gd))
                    semantic_deduped.remove(existing_gd)
                    _existing_word_sets.append((desc_ws, gd))
                    semantic_deduped.append(gd)
                    logger.debug(
                        "Semantic dedup: replaced (sim=%.2f) '%s' with higher-severity '%s'",
                        sim, existing_gd.get("description", "")[:60], gd.get("description", "")[:60],
                    )
                else:
                    logger.debug(
                        "Semantic dedup: dropped (sim=%.2f) '%s'",
                        sim, gd.get("description", "")[:60],
                    )
                is_dup = True
                break
        if not is_dup:
            _existing_word_sets.append((desc_ws, gd))
            semantic_deduped.append(gd)

    if len(final_deduped) != len(semantic_deduped):
        logger.info(
            "Semantic dedup: %d → %d gaps (removed %d near-duplicates, threshold=%.0f%%)",
            len(final_deduped), len(semantic_deduped),
            len(final_deduped) - len(semantic_deduped),
            _SEMANTIC_SIM_THRESHOLD * 100,
        )
    final_deduped = semantic_deduped

    # ── Sort deterministically: severity → normalized_qid → description ──────
    final_deduped.sort(key=lambda g: (
        _severity_rank.get(g.get("severity", "medium"), 2),
        _normalize_qid(g.get("related_question_id") or ""),
        _desc_key(g.get("description", "")),
    ))

    gaps = []
    for gd in final_deduped:
        desc = gd.get("description", "").strip()
        if not desc:
            continue
        gap_type = gd.get("gap_type", "unknown")
        related_qid = gd.get("related_question_id") or ""
        gaps.append({
            "id": str(uuid.uuid5(_NS, f"gap:{gap_type}:{related_qid}:{desc[:200]}")),
            "gap_type": gap_type,
            "description": desc,
            "severity": gd.get("severity", "medium"),
            "confidence": gd.get("confidence"),
            "related_question_id": gd.get("related_question_id"),
            "source_refs": gd.get("source_refs"),
            "evidence_assessment": gd.get("evidence_assessment"),
        })

    logger.info("FINAL LLM gap count after post-processing: %d", len(gaps))

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3: Merge deterministic + LLM gaps
    # ══════════════════════════════════════════════════════════════════════════
    # Deterministic gaps (unanswered questions) come first, then LLM evidence gaps.
    # Remove any LLM gap that accidentally covers an unanswered question.
    llm_gap_qids = set()
    filtered_llm_gaps = []
    for g in gaps:
        qid = g.get("related_question_id") or ""
        if qid in _unanswered_qid_set:
            logger.debug("Removing LLM gap for already-handled unanswered Q: %s", qid)
            continue
        filtered_llm_gaps.append(g)
        if qid:
            llm_gap_qids.add(qid)

    logger.info(
        "[MERGE] Deterministic: %d gaps | LLM evidence: %d gaps (removed %d overlapping)",
        len(deterministic_gaps), len(filtered_llm_gaps), len(gaps) - len(filtered_llm_gaps),
    )

    # Combine: deterministic first, then LLM evidence gaps
    all_gaps = deterministic_gaps + filtered_llm_gaps

    # Final sort: severity → question_id → description
    _severity_rank_final = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_gaps.sort(key=lambda g: (
        _severity_rank_final.get(g.get("severity", "medium"), 2),
        _normalize_qid(g.get("related_question_id") or "") or "ZZZZ",
        (g.get("description") or "")[:120].lower(),
    ))

    logger.info("TOTAL gaps (deterministic + LLM): %d", len(all_gaps))

    return {
        "gaps": all_gaps,
        "security_questions_searched": searched_questions,
        "evidence_chunks_matched": len(unique_evidence),
        "coverage_summary": {},
        "rag_evidence_sample": unique_evidence[:20],
    }
