"""
Assessment Input Fingerprint
============================
Generates a deterministic SHA-256 fingerprint of all inputs that affect
the LLM assessment output. Used by the version-level cache to decide
whether a new assessment has the same input as a previous version.

The fingerprint includes:
  - SHA-256 of every uploaded file's bytes (questionnaires, artifacts,
    policies, contract clauses)
  - IDs of retrieved evidence chunks (captures default policy/clause version)
  - Prompt template versions (catches prompt edits)
  - Model name (catches model upgrades)
  - Judge enabled state (ON vs OFF produces different final outputs)

None of this touches any business logic, scoring, or report structure.
"""
import hashlib
import json
import logging
import os

logger = logging.getLogger("tprm.fingerprint")

# ── Prompt template version ────────────────────────────────────────────────────
# Increment these manually whenever the corresponding YAML prompt is edited,
# so that cached LLM responses are invalidated.
_DRAFT_PROMPT_VERSION  = "v1.0"
_JUDGE_PROMPT_VERSION  = "v1.0"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def compute_fingerprint(
    file_bytes_by_category: dict[str, list[tuple[str, bytes]]],
    retrieved_chunk_ids: list[str],
    llm_judge_enabled: bool,
) -> str:
    """
    Compute a deterministic fingerprint for the full assessment input.

    Parameters
    ----------
    file_bytes_by_category : dict
        {category: [(filename, bytes), ...]} for every uploaded file.
        Categories: questionnaires, artifacts, policies, contract_clauses,
                    pre_business_assessment.
    retrieved_chunk_ids : list[str]
        Sorted list of chunk IDs selected by RAG retrieval for this run.
        Captures which default policy/clause version was active.
    llm_judge_enabled : bool
        Whether the judge pass is enabled (affects final output).
    """
    h = hashlib.sha256()

    # 1. File hashes — sorted for stability regardless of upload order
    for category in sorted(file_bytes_by_category.keys()):
        files = sorted(file_bytes_by_category[category], key=lambda t: t[0])
        for filename, data in files:
            h.update(f"{category}:{filename}:".encode())
            h.update(_sha256_bytes(data).encode())

    # 2. Retrieved chunk IDs — deterministic representation of policy/clause version
    for chunk_id in sorted(retrieved_chunk_ids):
        h.update(chunk_id.encode())

    # 3. Prompt versions — invalidates cache when prompts are edited
    h.update(_DRAFT_PROMPT_VERSION.encode())
    h.update(_JUDGE_PROMPT_VERSION.encode())

    # 4. Model name
    model = os.getenv("OPENAI_MODEL", "gpt-5.4-azure")
    h.update(model.encode())

    # 5. Judge state — ON vs OFF produces a different final report
    h.update(str(llm_judge_enabled).encode())

    fingerprint = h.hexdigest()
    logger.debug("Fingerprint computed: %s", fingerprint[:16])
    return fingerprint


# ── DB persistence (stored inside assessment's pipeline_outputs) ───────────────
# We do NOT add new DB columns — the fingerprint is stored as a pipeline_output
# row under step_name="assessment_fingerprint", which already exists as a JSONB
# column in the pipeline_outputs table.

def save_fingerprint(assessment_id: str, fingerprint: str) -> None:
    """Persist the fingerprint for this assessment version."""
    try:
        from webapp.db_storage import save_pipeline_output
        save_pipeline_output(assessment_id, "assessment_fingerprint", {
            "fingerprint": fingerprint,
        })
        logger.info("Fingerprint saved for %s: %s…", assessment_id, fingerprint[:16])
    except Exception as exc:
        logger.warning("Could not save fingerprint for %s: %s", assessment_id, exc)


def get_fingerprint(assessment_id: str) -> str | None:
    """Load the stored fingerprint for a given assessment."""
    try:
        from webapp.db_storage import get_pipeline_output
        row = get_pipeline_output(assessment_id, "assessment_fingerprint")
        if row:
            return row.get("fingerprint")
    except Exception as exc:
        logger.warning("Could not load fingerprint for %s: %s", assessment_id, exc)
    return None


def find_matching_version(
    vendor_id: str,
    current_assessment_id: str,
    fingerprint: str,
) -> dict | None:
    """
    Search all completed versions of the same vendor for a matching fingerprint.
    Returns the assessment metadata dict of the matching version, or None.

    Only looks at COMPLETED assessments so we never reuse a failed/partial result.
    """
    try:
        from webapp.db_storage import list_assessments, get_pipeline_output, get_report_data
        all_assessments = list_assessments()
        candidates = [
            a for a in all_assessments
            if a.get("vendor_id") == vendor_id
            and a["id"] != current_assessment_id
            and a.get("status") == "completed"
        ]
        # Check most recent first
        candidates.sort(key=lambda a: a.get("version", 0), reverse=True)
        for candidate in candidates:
            stored = get_fingerprint(candidate["id"])
            if stored == fingerprint:
                # Confirm the candidate actually has a report
                report = get_report_data(candidate["id"])
                if report:
                    logger.info(
                        "Cache HIT: current=%s matches v%s (%s)",
                        current_assessment_id, candidate.get("version"), candidate["id"],
                    )
                    return candidate
    except Exception as exc:
        logger.warning("Fingerprint search failed: %s", exc)
    return None
