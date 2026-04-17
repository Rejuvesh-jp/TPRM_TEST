"""
Pipeline Runner — Web Context
==============================
Wraps the 7-step TPRM assessment pipeline for web use.
Runs in a background thread with progress updates via storage metadata.
"""
import json
import logging
import os
import random
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')
from dotenv import load_dotenv

# Load .env so OPENAI_API_KEY is available
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Fix Windows console encoding ────────────────────────
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.ocr_service import extract_text, SUPPORTED_EXTENSIONS
from services.embedding_service import (
    mock_embed_text, mock_embed_texts,
    cosine_similarity, similarity_search, EMBEDDING_DIM,
    _get_cached_embedding, _put_cached_embedding, _get_cached_embeddings_batch,
)
from services.questionnaire_parser import (
    parse_sig_lite_pdf, parse_generic_questionnaire,
    build_questions_with_embeddings,
    get_all_control_ids, INFO_ONLY_SECTIONS,
)
from services.artifact_processor import process_artifacts, discover_files
from services.policy_processor import process_policies
from services.clause_processor import process_clauses
from services.gap_analysis_service import run_gap_analysis
# from services.risk_assessment_service import run_risk_assessment  # kept as backup
from services.remedial_plan_service import run_remedial_plan
from services.recommendation_service import run_recommendations
from services.llm_judge import run_llm_judge_multi_pass
from services.assessment_fingerprint import (
    compute_fingerprint, save_fingerprint,
    find_matching_version,
)
from webapp.pg_vector_store import PgVectorStore

from webapp.db_storage import (
    update_status, update_progress,
    get_uploaded_files, save_pipeline_output, save_report_data,
    get_default_processed_data, get_report_data,
    STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED,
)
from webapp.config import LLM_JUDGE_ENABLED, LLM_CACHE_ENABLED

logger = logging.getLogger("tprm.pipeline_runner")

# ── Pre-Assessment Sensitivity Auto-Scoring ──────────────────────────────────
# Each tuple: (keywords to match in question text, yes_score)
_PA_RULES = [
    (["cloud", "saas", "paas", "iaas"], 5),
    (["physical", "logical", "access", "infrastructure"], 5),
    (["connecting", "outside titan", "outside network", "external network", "non titan", "non-titan"], 5),
    (["developing", "hardware", "software", "processing data", "on behalf"], 5),
    (["pii", "personally identifiable", "personal data", "customer", "employee"], 20),
    (["financial data", "financial information"], 20),
    (["hosted on supplier", "hosted on vendor", "supplier premises", "vendor premises"], 5),
    (["incident", "breach", "security incident"], 5),
    (["payment card", "credit card", "pci", "cardholder"], 20),
    (["business continuity", "disaster recovery", "bcp", "drp", "failure"], 20),
]

_PA_QUESTION_TEXTS = [
    "Is the third party solution a Cloud service (e.g. SaaS, PaaS, IaaS)?",
    "Does the vendor or its employees have physical / logical access to Titan infrastructure?",
    "Is the third party connecting to the network outside Titan network / systems?",
    "Is the third party developing hardware, software and/or processing data on behalf of Titan?",
    "Does the vendor have access to Titan's PII (Personally Identifiable Information) data of customers or employee?",
    "Is the vendor processing any financial data?",
    "Is Titan's information / systems hosted on supplier premises?",
    "Has the third party solution or service had an incident (breach) in the past 12 months?",
    "Does the vendor have access to payment card information?",
    "Would a failure of this vendor's systems or processes cause Titan to activate its Business Continuity Plan or Disaster Recovery Plan?",
]


def _score_pre_assessment(all_questions: list[dict]) -> dict | None:
    """Match parsed pre-BA questions against the 10 known scoring questions.

    Uses keyword matching with exclusive assignment — once a parsed question
    is matched to a rule, it is removed from the pool so no other rule can
    grab it and produce a wrong answer.

    Returns None if no pre-BA questions were found, otherwise returns:
    {"responses": [...], "total_score": N, "sensitivity": "low"|"medium"|"high"}
    """
    if not all_questions:
        return None

    q_lower = [(q.get("question_text", "").lower(), q.get("response_text", "").strip().lower()) for q in all_questions]

    # ── Phase 1: Build a score matrix (rule_idx, question_idx) → hits ────
    candidates = []
    for rule_idx, (keywords, _yes_score) in enumerate(_PA_RULES):
        for q_idx, (qt, _rt) in enumerate(q_lower):
            hits = sum(1 for kw in keywords if kw in qt)
            if hits > 0:
                candidates.append((hits, rule_idx, q_idx))

    # Sort descending by hits so the strongest matches are assigned first
    candidates.sort(key=lambda x: x[0], reverse=True)

    # ── Phase 2: Greedy exclusive assignment ─────────────────────────────
    assigned_rules: dict[int, int] = {}   # rule_idx → q_idx
    used_questions: set[int] = set()

    for hits, rule_idx, q_idx in candidates:
        if rule_idx in assigned_rules or q_idx in used_questions:
            continue
        assigned_rules[rule_idx] = q_idx
        used_questions.add(q_idx)

    # ── Phase 3: Score each rule ─────────────────────────────────────────
    breakdown = []
    total = 0

    for idx, (keywords, yes_score) in enumerate(_PA_RULES):
        q_num = idx + 1
        matched = idx in assigned_rules

        if matched:
            q_idx = assigned_rules[idx]
            _qt, rt = q_lower[q_idx]
            is_yes = rt.startswith("yes") or rt == "y" or rt == "true"
            matched_answer = "yes" if is_yes else "no"
        else:
            matched_answer = "no"

        score = yes_score if matched_answer == "yes" else 0
        total += score
        breakdown.append({
            "q": q_num,
            "text": _PA_QUESTION_TEXTS[idx],
            "answer": matched_answer,
            "score": score,
            "max_score": yes_score,
            "matched": matched,
        })

    if total <= 10:
        sensitivity = "low"
    elif total <= 20:
        sensitivity = "medium"
    else:
        sensitivity = "high"

    matched_count = sum(1 for b in breakdown if b["matched"])
    if matched_count == 0:
        return None  # No questions matched — can't determine sensitivity

    return {"responses": breakdown, "total_score": total, "sensitivity": sensitivity}


# ── Per-step performance timer ────────────────────────────────────────────────
from contextlib import contextmanager

@contextmanager
def _perf_step(name: str):
    """Log elapsed time for a named pipeline step."""
    t = time.perf_counter()
    logger.info("[PERF] ▶  %s ...", name)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t
        logger.info("[PERF] ✔  %-40s %.1fs", name, elapsed)
# ─────────────────────────────────────────────────────────────────────────────

# ── Import mock LLM and prompt logic from run_assessment ──
from run_assessment import (
    mock_call_llm_json,
    PROMPT_TEMPLATES, render_prompt, get_system_prompt,
    chunk_text,
    _generate_markdown_summary,
)


import shutil
import tempfile


def _write_temp_files(assessment_id: str, category: str, temp_dir: Path):
    """Extract uploaded files from DB to a temporary directory for processing."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    files = get_uploaded_files(assessment_id, category)
    for filename, file_data in files:
        (temp_dir / filename).write_bytes(file_data)
    return temp_dir


def run_pipeline_async(assessment_id: str, user_email: str = None):
    """Launch the pipeline in a background thread."""
    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(assessment_id, user_email),
        daemon=True,
    )
    thread.start()
    return thread


def _run_pipeline_thread(assessment_id: str, user_email: str = None):
    """Execute the full 7-step pipeline for an assessment."""
    try:
        update_status(assessment_id, STATUS_RUNNING,
                      started_at=datetime.now(timezone.utc).isoformat())
        _run_pipeline(assessment_id, user_email=user_email)
        update_status(assessment_id, STATUS_COMPLETED,
                      completed_at=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        logger.exception("Pipeline failed for %s", assessment_id)
        update_status(assessment_id, STATUS_FAILED,
                      error=str(exc),
                      completed_at=datetime.now(timezone.utc).isoformat())


def _run_pipeline(assessment_id: str, user_email: str = None):
    from webapp.db_storage import get_assessment
    from services.llm_cache import clear_cache as _clear_llm_session_cache
    from services.embedding_service import clear_embedding_cache as _clear_emb_cache
    _clear_llm_session_cache()  # clear in-memory layer only; DB cache is preserved for cross-run determinism
    _clear_emb_cache()          # clear in-memory embedding cache; DB embedding cache is preserved

    t0 = time.time()
    meta = get_assessment(assessment_id)
    use_openai = meta.get("use_openai", False)
    vendor_name_hint = meta.get("vendor_name", "Unknown")

    # Create temp directory for file-based processors
    temp_base = Path(tempfile.mkdtemp(prefix=f"tprm_{assessment_id[:8]}_"))
    quest_dir = temp_base / "questionnaires"
    artifact_dir = temp_base / "artifacts"
    policy_dir = temp_base / "policies"
    clause_dir = temp_base / "contract_clauses"

    try:
        _run_pipeline_inner(assessment_id, meta, use_openai, vendor_name_hint,
                            t0, temp_base, quest_dir, artifact_dir, policy_dir, clause_dir,
                            user_email=user_email)
    finally:
        # Clean up temp files
        shutil.rmtree(temp_base, ignore_errors=True)


def _run_pipeline_inner(assessment_id, meta, use_openai, vendor_name_hint,
                        t0, temp_base, quest_dir, artifact_dir, policy_dir, clause_dir,
                        user_email=None):
    # Extract uploaded files from DB to temp directories
    _write_temp_files(assessment_id, "questionnaires", quest_dir)
    _write_temp_files(assessment_id, "artifacts", artifact_dir)
    # Only write policy/clause temp files if user actually uploaded them
    # (if using defaults, we skip file I/O entirely)
    user_has_policies = bool(get_uploaded_files(assessment_id, "policies"))
    user_has_clauses = bool(get_uploaded_files(assessment_id, "contract_clauses"))
    if user_has_policies:
        _write_temp_files(assessment_id, "policies", policy_dir)
    if user_has_clauses:
        _write_temp_files(assessment_id, "contract_clauses", clause_dir)

    # ── Log runtime configuration ────────────────────────────────────────────
    logger.info(
        "[CONFIG] LLM Judge: %s | Version Report Cache: %s",
        "enabled" if LLM_JUDGE_ENABLED else "disabled",
        "enabled" if LLM_CACHE_ENABLED else "disabled",
    )
    if not LLM_CACHE_ENABLED:
        logger.info(
            "[CONFIG] Fresh run triggered — Version Report Cache is OFF. "
            "Full pipeline will execute for every version regardless of prior results."
        )

    # ── Version-level cache: check input fingerprint before running the pipeline ──
    # Load raw bytes for all uploaded categories — needed for fingerprinting.
    # This is cheap (bytes are already in DB); we avoid re-reading temp files.
    if LLM_CACHE_ENABLED:
        _fp_bytes: dict[str, list[tuple[str, bytes]]] = {}
        for _cat in ("questionnaires", "artifacts", "policies", "contract_clauses",
                     "pre_business_assessment"):
            _files = get_uploaded_files(assessment_id, _cat)
            if _files:
                _fp_bytes[_cat] = _files

        # We don't yet know the chunk IDs at this point (computed during Step 2),
        # so we omit them here. The fingerprint is still highly discriminating
        # because every file byte difference changes the hash.
        _fp = compute_fingerprint(
            file_bytes_by_category=_fp_bytes,
            retrieved_chunk_ids=[],          # populated post-embedding; see below
            llm_judge_enabled=LLM_JUDGE_ENABLED,
        )
        _vendor_id = meta.get("vendor_id", "")
        _cached_version = find_matching_version(_vendor_id, assessment_id, _fp)
        if not _cached_version:
            logger.info(
                "[CACHE] Cache miss — fingerprint does not match any prior version for vendor '%s'. "
                "Running full pipeline fresh.",
                _vendor_id,
            )
        if _cached_version:
            cached_report = get_report_data(_cached_version["id"])
            if cached_report:
                logger.info(
                    "Cache HIT — reusing report from v%s (%s)",
                    _cached_version.get("version"), _cached_version["id"],
                )
                cached_report["_cache_source"] = {
                    "reused_from": _cached_version["id"],
                    "version": _cached_version.get("version"),
                }
                save_report_data(assessment_id, cached_report)
                save_pipeline_output(assessment_id, "assessment_report", cached_report)
                save_fingerprint(assessment_id, _fp)
                elapsed = time.time() - t0
                summary_data = cached_report.get("summary", {})
                summary_data["elapsed_seconds"] = round(elapsed, 2)
                summary_data["_cache_hit"] = True
                update_status(assessment_id, STATUS_COMPLETED,
                              summary=summary_data,
                              completed_at=datetime.now(timezone.utc).isoformat())
                return  # Pipeline short-circuited by version cache

    # ── Choose real or mock implementations ──
    if use_openai:
        from services.embedding_service import openai_embed_text, openai_embed_texts
        from openai import OpenAI

        from webapp.obo_token import get_openai_key
        api_key = get_openai_key(user_email)
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not found. Set it in .env file or environment variables."
            )
        logger.info("Using OpenAI mode (key: %s...%s)", api_key[:8], api_key[-4:])

        embed_fn = openai_embed_text
        embed_batch_fn = openai_embed_texts
        import httpx
        # verify=True: validate TLS certificates. Override via OPENAI_SSL_VERIFY=false or TPRM_SSL_VERIFY=false.
        _ssl_false = {"false", "0", "no"}
        _ssl_verify = (
            os.getenv("OPENAI_SSL_VERIFY", "true").lower() not in _ssl_false
            and os.getenv("TPRM_SSL_VERIFY", "true").lower() not in _ssl_false
        )
        _gateway_base = "https://ai.titan.in/gateway"

        def _fresh_client():
            """Build an OpenAI client with a freshly acquired token on every call."""
            fresh_key = get_openai_key(user_email)
            if not fresh_key:
                raise RuntimeError("OPENAI_API_KEY not found — set it in .env or log in via SSO.")
            return OpenAI(
                api_key=fresh_key,
                http_client=httpx.Client(verify=_ssl_verify),
                base_url=_gateway_base,
            )

        # Wrap embed functions to use fresh token on every call
        # (avoids the singleton client in embedding_service.py which caches a stale key)

        def embed_fn(text: str, model: str = "azure/text-embedding-3-small") -> list:
            truncated = text[:8000]
            cached = _get_cached_embedding(truncated)
            if cached is not None:
                return cached
            response = _fresh_client().embeddings.create(
                model="azure/text-embedding-3-small", input=truncated
            )
            emb = response.data[0].embedding
            _put_cached_embedding(truncated, emb)
            return emb

        def embed_batch_fn(texts: list, model: str = "azure/text-embedding-3-small",
                           batch_size: int = 100) -> list:
            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = [t[:8000] for t in texts[i:i + batch_size]]
                # One DB round-trip for the whole batch instead of N individual queries
                cached_results = _get_cached_embeddings_batch(batch)
                to_fetch_indices = [idx for idx, c in enumerate(cached_results) if c is None]
                if to_fetch_indices:
                    to_fetch_texts = [batch[idx] for idx in to_fetch_indices]
                    api_resp = _fresh_client().embeddings.create(
                        model="azure/text-embedding-3-small", input=to_fetch_texts
                    )
                    for idx, api_item in zip(to_fetch_indices, api_resp.data):
                        emb = api_item.embedding
                        _put_cached_embedding(batch[idx], emb)
                        cached_results[idx] = emb
                all_embeddings.extend(cached_results)
            return all_embeddings

        def llm_fn(prompt, system_prompt="", **kw):
            import time as _time
            model = os.getenv("OPENAI_MODEL", "gpt-5.4-azure")
            max_retries = 3
            last_err = None

            for attempt in range(1, max_retries + 1):
                try:
                    response = _fresh_client().chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0,
                        max_tokens=16384,
                        seed=42,
                        response_format={"type": "json_object"},
                    )
                    content = response.choices[0].message.content
                    if content and content.strip():
                        result = json.loads(content)
                        return result
                    logger.warning("Model '%s' returned empty (attempt %d/%d)", model, attempt, max_retries)
                except json.JSONDecodeError as e:
                    logger.warning("Model '%s' returned invalid JSON (attempt %d/%d): %s", model, attempt, max_retries, str(e)[:100])
                    last_err = e
                except Exception as e:
                    error_msg = str(e)
                    if "insufficient_quota" in error_msg or "429" in error_msg or "QUOTA" in error_msg:
                        raise RuntimeError(
                            f"Titan AI Gateway quota exceeded — your USD quota has been exhausted. "
                            f"Please contact the AI Gateway admin to increase your quota "
                            f"or switch to Mock LLM mode. (Error: {error_msg[:200]})"
                        ) from e
                    if "401" in error_msg or "Unauthorized" in error_msg:
                        raise RuntimeError(
                            f"Titan AI Gateway authentication failed — your JWT token may have expired. "
                            f"Please generate a fresh token. (Error: {error_msg[:200]})"
                        ) from e
                    logger.warning("Model '%s' error (attempt %d/%d): %s", model, attempt, max_retries, error_msg[:150])
                    last_err = e
                if attempt < max_retries:
                    _time.sleep(2 * attempt)

            raise RuntimeError(
                f"Model '{model}' failed after {max_retries} attempts. "
                f"Last error: {str(last_err)[:200] if last_err else 'empty response'}"
            )
    else:
        embed_fn = mock_embed_text
        embed_batch_fn = mock_embed_texts
        llm_fn = mock_call_llm_json

    vs = PgVectorStore(assessment_id)

    # ═══════════════════════════════════════════════
    # STEP 1: Parse Questionnaire
    # ═══════════════════════════════════════════════
    update_progress(assessment_id, 1, "Parsing questionnaires")
    _t_step1 = time.perf_counter()

    q_files = discover_files(quest_dir, {".pdf"})
    questionnaires = []

    for qf in q_files:
        text = extract_text(str(qf))
        if not text.strip():
            continue
        parsed = parse_sig_lite_pdf(text)
        questions = build_questions_with_embeddings(parsed, embed_fn, embed_batch_fn)

        all_control_ids = get_all_control_ids(parsed)
        a_prompt = render_prompt(
            "questionnaire_analysis",
            vendor_name=parsed.get("vendor_name", vendor_name_hint),
            questionnaire_data=json.dumps(parsed, indent=2)[:15000],
        )
        a_prompt += "\n\n--- ALL CONTROL IDS ---\n" + json.dumps(
            [{"control_id": cid} for cid in all_control_ids]
        )
        analysis = llm_fn(a_prompt, system_prompt=get_system_prompt("questionnaire_analysis"))

        analysis_map = {
            item.get("control_id"): item
            for item in analysis.get("question_analysis", [])
            if item.get("control_id")
        }
        for question in questions:
            cid = question.get("control_id")
            if cid and cid in analysis_map:
                qa = analysis_map[cid]
                question["risk_relevance"] = qa.get("risk_relevance")
                question["claim_strength"] = qa.get("claim_strength")
                question["expected_evidence"] = qa.get("expected_evidence")
                question["flags"] = qa.get("flags")

        questionnaires.append({
            "id": str(uuid.uuid5(_NS, f"quest:{qf.name}")),
            "file_name": qf.name,
            "source_type": "questionnaire",
            "parsed_content": parsed,
            "analysis_result": analysis,
            "questions": questions,
        })

    sig_questionnaire_count = len(questionnaires)

    # ── Pre-Business Assessment questionnaires ──
    pre_ba_dir = temp_base / "pre_business_assessment"
    _write_temp_files(assessment_id, "pre_business_assessment", pre_ba_dir)
    pre_ba_files = discover_files(pre_ba_dir, SUPPORTED_EXTENSIONS)
    for pf in pre_ba_files:
        text = extract_text(str(pf))
        if not text.strip():
            continue
        parsed = parse_generic_questionnaire(text, llm_fn, pf.name)
        questions = build_questions_with_embeddings(parsed, embed_fn, embed_batch_fn)

        all_control_ids = get_all_control_ids(parsed)
        a_prompt = render_prompt(
            "questionnaire_analysis",
            vendor_name=parsed.get("vendor_name", vendor_name_hint),
            questionnaire_data=json.dumps(parsed, indent=2)[:15000],
        )
        a_prompt += "\n\n--- ALL CONTROL IDS ---\n" + json.dumps(
            [{"control_id": cid} for cid in all_control_ids]
        )
        analysis = llm_fn(a_prompt, system_prompt=get_system_prompt("questionnaire_analysis"))

        analysis_map = {
            item.get("control_id"): item
            for item in analysis.get("question_analysis", [])
            if item.get("control_id")
        }
        for question in questions:
            cid = question.get("control_id")
            if cid and cid in analysis_map:
                qa = analysis_map[cid]
                question["risk_relevance"] = qa.get("risk_relevance")
                question["claim_strength"] = qa.get("claim_strength")
                question["expected_evidence"] = qa.get("expected_evidence")
                question["flags"] = qa.get("flags")

        questionnaires.append({
            "id": str(uuid.uuid5(_NS, f"preba:{pf.name}")),
            "file_name": pf.name,
            "source_type": "pre_business_assessment",
            "parsed_content": parsed,
            "analysis_result": analysis,
            "questions": questions,
        })

    pre_ba_count = len(questionnaires) - sig_questionnaire_count
    total_questions = sum(len(q["questions"]) for q in questionnaires)

    # ── Auto-calculate engagement sensitivity from pre-BA responses ──
    if pre_ba_count > 0:
        pre_ba_questions = []
        for q_data in questionnaires:
            if q_data.get("source_type") == "pre_business_assessment":
                pre_ba_questions.extend(q_data.get("questions", []))
        pa_scores = _score_pre_assessment(pre_ba_questions)
        if pa_scores:
            sensitivity = pa_scores["sensitivity"]
            update_status(assessment_id, STATUS_RUNNING,
                          nature_of_engagement=sensitivity,
                          pre_assessment_scores=pa_scores)
            logger.info("Auto-scored pre-assessment: %s (score=%d, matched=%d/%d questions)",
                        sensitivity, pa_scores["total_score"],
                        sum(1 for b in pa_scores["responses"] if b["matched"]), 10)

    save_pipeline_output(assessment_id, "1_questionnaires", {
        "step": "1_document_ingestion_questionnaire",
        "total_questionnaires": len(questionnaires),
        "total_questions": total_questions,
        "questionnaires": [
            {
                "id": q["id"], "file_name": q["file_name"],
                "vendor_name": q["parsed_content"].get("vendor_name"),
                "parsed_content": q["parsed_content"],
                "analysis_result": q["analysis_result"],
                "questions": q["questions"],
            }
            for q in questionnaires
        ],
    })
    logger.info("[PERF] ✔  %-40s %.1fs", "Step 1: questionnaire parsing", time.perf_counter() - _t_step1)

    # ═══════════════════════════════════════════════
    # STEP 2: Policy & Clause Embeddings
    # ═══════════════════════════════════════════════
    update_progress(assessment_id, 2, "Processing policies & clauses")
    _t_step2 = time.perf_counter()

    # Check if user uploaded custom policies; if not, use preloaded defaults
    if user_has_policies:
        policies = process_policies(policy_dir, chunk_text, embed_fn)
        policies_source = "uploaded"
    else:
        default_policies = get_default_processed_data("policies")
        if default_policies:
            policies = default_policies
            policies_source = "default"
            logger.info("Using %d preloaded default policies (skipping embedding)", len(policies))
        else:
            policies = []
            policies_source = "none"

    # Check if user uploaded custom clauses; if not, use preloaded defaults
    if user_has_clauses:
        clauses = process_clauses(clause_dir, embed_fn)
        clauses_source = "uploaded"
    else:
        default_clauses = get_default_processed_data("contract_clauses")
        if default_clauses:
            clauses = default_clauses
            clauses_source = "default"
            logger.info("Using %d preloaded default clauses (skipping embedding)", len(clauses))
        else:
            clauses = []
            clauses_source = "none"

    # Only insert vectors into the per-assessment embeddings table for uploaded files.
    # For preloaded defaults, the data is already pre-computed — no need to duplicate
    # hundreds of 1536-dim vectors into the DB for every assessment.
    if policies_source == "uploaded":
        for p in policies:
            for c in p.get("chunks", []):
                vs.add("policy_vectors", {
                    "chunk_id": c["id"], "source_document": p["title"],
                    "chunk_text": c["content"], "embedding": c["embedding"],
                })

    if clauses_source == "uploaded":
        for cl in clauses:
            vs.add("clause_vectors", {
                "chunk_id": cl["id"], "source_document": cl["source_file"],
                "chunk_text": cl["content"], "embedding": cl["embedding"],
            })

    total_policy_chunks = sum(len(p.get("chunks", [])) for p in policies)
    logger.info("[PERF] ✔  %-40s %.1fs", "Step 2: policies & clauses", time.perf_counter() - _t_step2)

    # Save step 2 output — strip large embedding arrays to keep JSONB small
    save_pipeline_output(assessment_id, "2_policies_and_clauses", {
        "step": "2_policy_clause_embeddings",
        "policies_source": policies_source,
        "clauses_source": clauses_source,
        "total_policies": len(policies),
        "total_policy_chunks": total_policy_chunks,
        "total_contract_clauses": len(clauses),
        "policies": [
            {
                "id": p["id"], "title": p["title"],
                "total_chunks": len(p.get("chunks", [])),
                "chunks": [{"chunk_id": c["id"], "chunk_index": c["chunk_index"],
                             "content": c["content"]}
                            for c in p.get("chunks", [])],
            }
            for p in policies
        ],
        "contract_clauses": [
            {"id": cl["id"], "source_file": cl["source_file"],
             "category": cl["category"], "content": cl["content"]}
            for cl in clauses
        ],
    })

    # ═══════════════════════════════════════════════
    # STEP 3: Questionnaire Analysis
    # ═══════════════════════════════════════════════
    update_progress(assessment_id, 3, "Analysing questionnaire responses")
    _t_step3 = time.perf_counter()

    all_questions = []
    for q in questionnaires:
        all_questions.extend(q["questions"])

    missing_answers = [q for q in all_questions if not q.get("response_text")]
    weak_claims = [q for q in all_questions if q.get("claim_strength") is not None and q["claim_strength"] < 0.7]
    flagged = [q for q in all_questions if q.get("flags")]

    questionnaire_analysis = {
        "total_questions": len(all_questions),
        "missing_answers": len(missing_answers),
        "weak_claims": len(weak_claims),
        "flagged_questions": len(flagged),
        "missing_answer_controls": [q["control_id"] for q in missing_answers],
        "weak_claim_controls": [q["control_id"] for q in weak_claims],
        "questions_requiring_evidence": [
            q["control_id"] for q in all_questions
            if q.get("expected_evidence") and q.get("risk_relevance") in ("high", "critical")
        ],
    }

    save_pipeline_output(assessment_id, "3_questionnaire_analysis", {
        "step": "3_questionnaire_analysis", **questionnaire_analysis,
    })
    logger.info("[PERF] ✔  %-40s %.1fs", "Step 3: questionnaire analysis", time.perf_counter() - _t_step3)

    # ═══════════════════════════════════════════════
    # STEP 4: Artifact Analysis
    # ═══════════════════════════════════════════════
    update_progress(assessment_id, 4, "Processing vendor artifacts")
    _t_step4 = time.perf_counter()

    artifacts = process_artifacts(
        artifact_dir, chunk_text, embed_fn, embed_batch_fn,
        llm_fn, render_prompt, get_system_prompt,
    )

    for art in artifacts:
        for c in art.get("chunks", []):
            vs.add("artifact_vectors", {
                "chunk_id": c["id"], "source_document": art["file_name"],
                "chunk_text": c["content"], "embedding": c["embedding"],
            })

    total_chunks = sum(len(a.get("chunks", [])) for a in artifacts)

    save_pipeline_output(assessment_id, "4_artifacts", {
        "step": "4_artifact_analysis",
        "total_artifacts": len(artifacts), "total_chunks": total_chunks,
        "artifacts": [
            {
                "id": a["id"], "file_name": a["file_name"],
                "total_chunks": len(a["chunks"]),
                "chunks": [{"chunk_id": c["id"], "chunk_index": c["chunk_index"],
                             "content": c["content"], "metadata": c["metadata"]}
                            for c in a["chunks"]],
                "insights": a["insights"],
            }
            for a in artifacts
        ],
    })

    # Only save vectors that were actually buffered (uploaded, not defaults)
    if policies_source == "uploaded":
        vs.save("policy_vectors")
    if clauses_source == "uploaded":
        vs.save("clause_vectors")
    vs.save("artifact_vectors")
    logger.info("[PERF] ✔  %-40s %.1fs", "Step 4: artifact analysis + vector save", time.perf_counter() - _t_step4)

    # ═══════════════════════════════════════════════
    # STEP 5: Gap Analysis & Risk Assessment
    # ═══════════════════════════════════════════════
    update_progress(assessment_id, 5, "Running gap analysis")
    _t_step5 = time.perf_counter()

    # Load reference gaps from the most recent completed assessment for this vendor
    _reference_gaps = None
    _ref_vendor_id = meta.get("vendor_id", "")
    if _ref_vendor_id:
        try:
            from webapp.db_storage import get_previous_gaps_for_vendor
            _reference_gaps = get_previous_gaps_for_vendor(_ref_vendor_id, exclude_assessment_id=assessment_id)
            if _reference_gaps:
                logger.info("[REFERENCE] Loaded %d reference gaps from previous assessment for vendor %s",
                            len(_reference_gaps), _ref_vendor_id)
        except Exception as _ref_err:
            logger.warning("[REFERENCE] Could not load reference gaps: %s", _ref_err)

    gap_result = run_gap_analysis(
        all_questions, artifacts, policies, clauses,
        embed_fn, llm_fn, render_prompt, get_system_prompt,
        reference_gaps=_reference_gaps,
    )
    gaps = gap_result["gaps"]

    save_pipeline_output(assessment_id, "5_gap_analysis", {
        "step": "5_gap_analysis",
        "total_gaps": len(gaps),
        "security_questions_searched": gap_result["security_questions_searched"],
        "evidence_chunks_matched": gap_result["evidence_chunks_matched"],
        "severity_breakdown": {s: sum(1 for g in gaps if g["severity"] == s)
                               for s in {g["severity"] for g in gaps}},
        "coverage_summary": gap_result["coverage_summary"],
        "gaps": gaps,
        "rag_evidence_sample": gap_result["rag_evidence_sample"],
    })

    vendor_name = vendor_name_hint
    if questionnaires:
        vendor_name = questionnaires[0]["parsed_content"].get("vendor_name", vendor_name_hint)

    logger.info("[PERF] ✔  %-40s %.1fs", "Step 5: gap analysis", time.perf_counter() - _t_step5)

    # Risk assessment step skipped (kept as backup in services/risk_assessment_service.py)
    # Derive overall severity from gaps instead
    _severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    overall_gap_severity = "low"
    for g in gaps:
        if _severity_order.get(g["severity"], 0) > _severity_order.get(overall_gap_severity, 0):
            overall_gap_severity = g["severity"]
    if not gaps:
        overall_gap_severity = "low"

    # ═══════════════════════════════════════════════
    # STEP 6: Remedial Plan + Clause Recommendations
    # ═══════════════════════════════════════════════
    update_progress(assessment_id, 6, "Generating remedial plan")
    _t_step6 = time.perf_counter()

    remedial_actions = run_remedial_plan(
        gaps, vendor_name,
        llm_fn, render_prompt, get_system_prompt,
    )

    save_pipeline_output(assessment_id, "6_remedial_plan", {
        "step": "6_remedial_plan",
        "total_actions": len(remedial_actions),
        "remedial_actions": remedial_actions,
    })

    update_progress(assessment_id, 6, "Generating recommendations")

    recommendations = run_recommendations(
        gaps, clauses,
        embed_fn, llm_fn, render_prompt, get_system_prompt,
    )

    save_pipeline_output(assessment_id, "7_recommendations", {
        "step": "7_clause_recommendations",
        "total_recommendations": len(recommendations),
        "priority_breakdown": {p: sum(1 for r in recommendations if r.get("priority") == p)
                              for p in {r.get("priority") for r in recommendations}},
        "recommendations": recommendations,
    })
    logger.info("[PERF] ✔  %-40s %.1fs", "Step 6: remedial plan + recommendations", time.perf_counter() - _t_step6)

    # ═══════════════════════════════════════════════
    # STEP 7: Final Assessment Report
    # ═══════════════════════════════════════════════
    update_progress(assessment_id, 7, "Generating final report")

    elapsed = time.time() - t0

    # Compliance analysis
    compliant_areas, partially_compliant, non_compliant, missing_controls = [], [], [], []
    gap_sections = set()
    for g in gaps:
        refs = g.get("source_refs") or {}
        for cid in refs.get("questionnaire", []):
            sec = cid.split(".")[0] if "." in cid else ""
            gap_sections.add(sec)
        if g["severity"] == "critical":
            non_compliant.append(g["description"][:120])
        elif g["severity"] == "high":
            partially_compliant.append(g["description"][:120])
        if g["gap_type"] == "missing_artifact":
            missing_controls.append(g["description"][:120])

    all_sections = set()
    for q in all_questions:
        sec = q.get("control_id", "").split(".")[0] if q.get("control_id") else ""
        if sec:
            all_sections.add(sec)
    for s in sorted(all_sections - gap_sections):  # sorted() ensures deterministic order
        compliant_areas.append(f"Section {s}: No gaps identified")
    non_compliant.sort()
    partially_compliant.sort()
    missing_controls.sort()

    # ═══════════════════════════════════════════════
    # STEP 7a: LLM Judge (optional second review pass)
    # ═══════════════════════════════════════════════
    judge_result: dict = {}
    judge_corrections: list[str] = []

    # Judge runs only in real LLM mode — mock mode returns nonsense JSON instantly
    # and would produce meaningless "corrections".
    _judge_skipped_reason: str | None = None
    if LLM_JUDGE_ENABLED and not use_openai:
        _judge_skipped_reason = "mock_mode"
        logger.info(
            "[JUDGE] Skipped — assessment is in Mock LLM mode. "
            "The judge uses the same LLM and would produce random output. "
            "Enable OpenAI mode to use the judge."
        )

    if LLM_JUDGE_ENABLED and use_openai:
        update_progress(assessment_id, 7, "Running LLM quality review (multi-pass)")
        _t_judge = time.perf_counter()
        try:
            gaps, recommendations, remedial_actions, judge_result, judge_corrections = (
                run_llm_judge_multi_pass(
                    vendor_name=vendor_name,
                    gaps=gaps,
                    recommendations=recommendations,
                    remedial_actions=remedial_actions,
                    all_questions=all_questions,
                    artifacts=artifacts,
                    overall_risk_rating=overall_gap_severity,
                    llm_fn=llm_fn,
                )
            )
            # Re-derive overall severity after judge corrections (e.g. severity bumped up)
            overall_gap_severity = "low"
            for g in gaps:
                if _severity_order.get(g["severity"], 0) > _severity_order.get(overall_gap_severity, 0):
                    overall_gap_severity = g["severity"]
            _judge_elapsed = time.perf_counter() - _t_judge
            logger.info(
                    "[JUDGE] Multi-pass completed in %.2fs — %d correction(s) applied.",
                    _judge_elapsed, len(judge_corrections),
                )
            save_pipeline_output(assessment_id, "llm_judge", {
                "step": "llm_judge",
                "elapsed_seconds": round(_judge_elapsed, 2),
                "judge_result": judge_result,
                "corrections_applied": judge_corrections,
                "pass_details": judge_result.get("_pass_details", []),
            })
        except Exception as _je:
            logger.warning("LLM judge failed (using draft as final): %s", _je)
            _judge_skipped_reason = f"error: {str(_je)[:120]}"
        logger.info("[PERF] ✔  %-40s %.1fs", "Step 7a: LLM judge", time.perf_counter() - _t_judge)

    logger.info(
        "[SCORING] Final gap count: %d | Overall risk: %s",
        len(gaps), overall_gap_severity,
    )

    report = {
        "pipeline_mode": "mock" if not use_openai else "openai",
        "elapsed_seconds": round(elapsed, 2),
        "input_summary": {
            "questionnaires": sig_questionnaire_count,
            "pre_business_assessments": pre_ba_count,
            "total_questions": total_questions,
            "artifacts": len(artifacts),
            "total_chunks": total_chunks,
            "policies": len(policies),
            "contract_clauses": len(clauses),
        },
        "questionnaire_findings": {
            "vendor_name": vendor_name,
            "total_questions": total_questions,
            "missing_answers": questionnaire_analysis["missing_answers"],
            "weak_claims": questionnaire_analysis["weak_claims"],
            "flagged_questions": questionnaire_analysis["flagged_questions"],
        },
        "artifact_findings": {
            "total_artifacts": len(artifacts),
            "total_chunks": total_chunks,
            "evidence_coverage": gap_result["coverage_summary"],
        },
        "policy_compliance": {
            "compliant_areas": compliant_areas,
            "partially_compliant": partially_compliant,
            "non_compliant": non_compliant,
            "missing_controls": missing_controls,
        },
        "risk_rating": {
            "overall": overall_gap_severity,
            "breakdown": {s: sum(1 for g in gaps if g["severity"] == s)
                         for s in {g["severity"] for g in gaps}},
        },
        "recommended_clauses": [
            {"clause": rec["clause_text"], "justification": rec["justification"],
             "priority": rec.get("priority"), "existing_coverage": rec.get("existing_coverage")}
            for rec in recommendations
        ],
        "gaps": gaps,
        "remedial_plan": remedial_actions,
        "recommendations": recommendations,
        "llm_judge_enabled": LLM_JUDGE_ENABLED,
        "llm_judge_ran": LLM_JUDGE_ENABLED and use_openai and _judge_skipped_reason is None,
        "llm_judge_skipped_reason": _judge_skipped_reason,
        "llm_judge_corrections": judge_corrections,
        "summary": {
            "total_gaps": len(gaps),
            "total_remedial_actions": len(remedial_actions),
            "total_recommendations": len(recommendations),
            "gap_severity": {s: sum(1 for g in gaps if g["severity"] == s)
                            for s in {g["severity"] for g in gaps}},
            "overall_risk_rating": overall_gap_severity,
            "executive_summary": gap_result.get("coverage_summary", {}).get("summary", ""),
        },
    }

    save_report_data(assessment_id, report)
    save_pipeline_output(assessment_id, "assessment_report", report)

    # ── Store input fingerprint for future version cache lookups ──────────────
    # Only saved when cache is enabled — used by find_matching_version on next run.
    if LLM_CACHE_ENABLED:
        # Collect all chunk IDs used in gap analysis evidence for a richer fingerprint
        _all_chunk_ids = []
        for g in gaps:
            _all_chunk_ids.extend((g.get("source_refs") or {}).get("artifacts", []))
            _all_chunk_ids.extend((g.get("source_refs") or {}).get("policies", []))
        _fp_bytes2: dict[str, list[tuple[str, bytes]]] = {}
        for _cat in ("questionnaires", "artifacts", "policies", "contract_clauses",
                     "pre_business_assessment"):
            _files = get_uploaded_files(assessment_id, _cat)
            if _files:
                _fp_bytes2[_cat] = _files
        _final_fp = compute_fingerprint(
            file_bytes_by_category=_fp_bytes2,
            retrieved_chunk_ids=sorted(set(_all_chunk_ids)),
            llm_judge_enabled=LLM_JUDGE_ENABLED,
        )
        save_fingerprint(assessment_id, _final_fp)

    # Update metadata with summary
    summary_data = {
        "vendor_name": vendor_name,
        "total_questionnaires": sig_questionnaire_count,
        "total_pre_business_assessments": pre_ba_count,
        "total_questions": total_questions,
        "total_artifacts": len(artifacts),
        "total_policies": len(policies),
        "total_clauses": len(clauses),
        "total_gaps": len(gaps),
        "total_remedial_actions": len(remedial_actions),
        "total_recommendations": len(recommendations),
        "overall_risk_rating": overall_gap_severity,
        "executive_summary": report["summary"]["executive_summary"],
        "elapsed_seconds": round(elapsed, 2),
        "gap_severity": report["summary"]["gap_severity"],
        "llm_judge_enabled": LLM_JUDGE_ENABLED,
        "llm_cache_enabled": LLM_CACHE_ENABLED,
    }
    update_status(assessment_id, STATUS_COMPLETED,
                  summary=summary_data,
                  completed_at=datetime.now(timezone.utc).isoformat())

    logger.info("Pipeline completed for %s in %.1fs", assessment_id, elapsed)
