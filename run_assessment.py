"""
TPRM AI Assessment Pipeline — run_assessment.py
================================================
Runs the entire TPRM AI assessment pipeline as a local Python workflow.
No API server, no database, no vendor management.

Reads input files from folders, processes through the 7-step pipeline,
and writes structured outputs.

Inputs:
    inputs/policy/           - TPRM Policy PDF (may be scanned → OCR)
    inputs/clauses/          - Infosec Contract Clause DOCX files
    inputs/pre_assessment/   - Business Pre-Assessment PDF (OneTrust export)
    inputs/questionnaire/    - SIG Lite Questionnaire PDF(s)
    inputs/artifacts/        - Vendor artifact PDFs/DOCX/ZIP files

Outputs:
    outputs/assessment_report.json   - Full structured assessment
    outputs/assessment_summary.md    - Human-readable summary

Vector Store:
    vector_store/policy_vectors.json
    vector_store/clause_vectors.json
    vector_store/artifact_vectors.json

Usage:
    python run_assessment.py
    python run_assessment.py --use-openai
    python run_assessment.py --max-artifacts 5
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path

import numpy as np

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

# ── Fix Windows console encoding ────────────────────────
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Project root ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Import services ──────────────────────────────────────
from services.ocr_service import extract_text, SUPPORTED_EXTENSIONS
from services.embedding_service import (
    mock_embed_text, mock_embed_texts,
    cosine_similarity, similarity_search,
    EMBEDDING_DIM,
)
from services.questionnaire_parser import (
    parse_sig_lite_pdf, build_questions_with_embeddings,
    get_all_control_ids, INFO_ONLY_SECTIONS,
)
from services.artifact_processor import process_artifacts, discover_files
from services.policy_processor import process_policies
from services.clause_processor import process_clauses
from services.gap_analysis_service import run_gap_analysis
from services.risk_assessment_service import run_risk_assessment
from services.recommendation_service import run_recommendations
from vector_store.json_vector_store import JsonVectorStore

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tprm.pipeline")

# ── Directories ──────────────────────────────────────────
INPUTS_DIR = PROJECT_ROOT / "inputs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
VECTOR_STORE_DIR = PROJECT_ROOT / "vector_store"

# Support both old and new folder names for backward compatibility
POLICY_DIRS = [INPUTS_DIR / "policy", INPUTS_DIR / "policies"]
CLAUSE_DIRS = [INPUTS_DIR / "clauses", INPUTS_DIR / "contract_clauses"]
PRE_ASSESSMENT_DIR = INPUTS_DIR / "pre_assessment"
QUESTIONNAIRE_DIRS = [INPUTS_DIR / "questionnaire", INPUTS_DIR / "questionnaires"]
ARTIFACT_DIR = INPUTS_DIR / "artifacts"


def _find_dir(candidates: list[Path]) -> Path | None:
    """Return the first existing directory from candidates."""
    for d in candidates:
        if d.exists():
            return d
    return candidates[0]  # return first as default even if not exists


# ═══════════════════════════════════════════════════════════════════
#  MOCK LLM (used when --use-openai is not set)
# ═══════════════════════════════════════════════════════════════════

def mock_call_llm_json(prompt: str, system_prompt: str = "", **kw) -> dict:
    """Return plausible mock LLM output based on detected prompt type."""
    _rng = random.Random(42)

    sp = (system_prompt + " " + prompt).lower()

    # ── Questionnaire parsing ────────────────────────────
    if "parse the following sig lite" in sp or "questionnaire text:" in sp:
        return {"vendor_name": "Adobe", "questionnaire_type": "SIG Lite",
                "total_questions": 0, "sections": []}

    # ── Questionnaire analysis ───────────────────────────
    if "analyze the following parsed questionnaire" in sp:
        control_ids = re.findall(r'"control_id":\s*"([^"]+)"', prompt)

        HIGH_RISK_SECTIONS = {"A", "B", "C", "D", "F", "G", "H", "I", "J",
                              "K", "L", "M", "N", "P", "T", "U", "V"}
        MEDIUM_SECTIONS = {"E", "O"}

        question_analysis = []
        control_coverage = {}

        for cid in control_ids:
            section_letter = cid.split(".")[0] if "." in cid else "?"
            if section_letter in HIGH_RISK_SECTIONS:
                risk = _rng.choice(["high", "critical", "high", "high"])
                strength = round(_rng.uniform(0.6, 0.95), 2)
                flags = ["weak_response"] if strength < 0.7 else []
                coverage = _rng.choice(["strong", "strong", "adequate"])
            elif section_letter in MEDIUM_SECTIONS:
                risk = _rng.choice(["medium", "low", "medium"])
                strength = round(_rng.uniform(0.5, 0.85), 2)
                flags = []
                coverage = "adequate"
            else:
                risk = "low"
                strength = round(_rng.uniform(0.7, 0.95), 2)
                flags = []
                coverage = "informational"

            question_analysis.append({
                "control_id": cid,
                "risk_relevance": risk,
                "claim_strength": strength,
                "expected_evidence": f"Supporting documentation for {cid}",
                "flags": flags,
            })
            sec_name = section_letter
            if sec_name not in control_coverage:
                control_coverage[sec_name] = coverage

        return {
            "vendor_profile": "Vendor demonstrates a mature security posture with ISO 27001 alignment.",
            "control_coverage": control_coverage,
            "overall_risk_indicators": [
                "Partial access reviews may leave ungoverned SaaS accounts",
                "No evidence of regular third-party penetration testing",
                "Business continuity plan reference missing",
                "Several document request items remain unanswered",
            ],
            "question_analysis": question_analysis,
        }

    # ── Artifact insights ────────────────────────────────
    if "analyze the following vendor artifact" in sp:
        return {
            "document_type": "policy",
            "policy_coverage": ["data_protection", "access_control", "incident_response"],
            "certifications": ["ISO 27001", "SOC 2 Type II"],
            "security_controls": [
                {"control": "Encryption at rest", "description": "AES-256 encryption for data at rest", "maturity": "high"},
                {"control": "Access logging", "description": "Centralized access logging with 12-month retention", "maturity": "high"},
            ],
            "compliance_indicators": ["GDPR", "SOC 2", "ISO 27001"],
            "key_findings": [
                "Document describes mature security controls",
                "Encryption and logging practices aligned with industry standards",
            ],
            "confidence": 0.80,
        }

    # ── Gap analysis — dynamic ───────────────────────────
    if "perform gap analysis" in sp:
        control_ids = re.findall(r'"control_id":\s*"([^"]+)"', prompt)
        risk_map = {}
        for m in re.finditer(r'"control_id":\s*"([^"]+)".*?"risk_relevance":\s*"([^"]*)"', prompt, re.DOTALL):
            risk_map[m.group(1)] = m.group(2)
        strength_map = {}
        for m in re.finditer(r'"control_id":\s*"([^"]+)".*?"claim_strength":\s*([\d.]+)', prompt, re.DOTALL):
            strength_map[m.group(1)] = float(m.group(2))
        evidence_chunks = re.findall(r'"matched_question":\s*"([^"]+)"', prompt)
        evidenced_controls = set(evidence_chunks)

        SIG_SECTIONS = {
            "A": "Enterprise Risk Management", "B": "Nth Party Management",
            "C": "Information Assurance", "D": "Asset and Info Management",
            "E": "Human Resources Security", "F": "Physical and Environmental Security",
            "G": "IT Operations Management", "H": "Access Control",
            "I": "Application Security", "J": "Cybersecurity Incident Mgmt.",
            "K": "Operational Resilience", "L": "Compliance Management",
            "M": "Endpoint Security", "N": "Network Security",
            "O": "Environmental, Social and Governance",
            "P": "Privacy Management", "T": "Threat Management",
            "U": "Server Security", "V": "Cloud Hosting Services",
        }

        gaps = []
        section_controls = {}
        for cid in control_ids:
            sec = cid.split(".")[0] if "." in cid else cid
            if sec in SIG_SECTIONS:
                section_controls.setdefault(sec, []).append(cid)

        for sec_letter in sorted(section_controls.keys()):
            sec_cids = section_controls[sec_letter]
            sec_name = SIG_SECTIONS.get(sec_letter, sec_letter)
            has_evidence = sum(1 for c in sec_cids if c in evidenced_controls)
            total = len(sec_cids)
            high_risk_cids = [c for c in sec_cids if risk_map.get(c) in ("high", "critical")]
            weak_cids = [c for c in sec_cids if strength_map.get(c, 1.0) < 0.7]

            if high_risk_cids and has_evidence < total:
                gap_type = _rng.choice(["missing_artifact", "unsupported_claim", "weak_evidence"])
                severity = "critical" if len(high_risk_cids) >= 2 else "high"
                gaps.append({
                    "gap_type": gap_type,
                    "description": (f"Section {sec_letter} ({sec_name}): {len(high_risk_cids)} high/critical-risk "
                                    f"control(s) ({', '.join(high_risk_cids[:5])}) lack sufficient artifact evidence. "
                                    f"Only {has_evidence}/{total} controls have matching documentation."),
                    "severity": severity,
                    "related_question_id": high_risk_cids[0],
                    "source_refs": {
                        "questionnaire": high_risk_cids[:5],
                        "artifacts": list(evidenced_controls & set(sec_cids))[:3],
                        "policies": [],
                        "contracts": [],
                    },
                    "evidence_assessment": f"{has_evidence}/{total} controls evidenced",
                })
            elif weak_cids:
                gaps.append({
                    "gap_type": "weak_evidence",
                    "description": (f"Section {sec_letter} ({sec_name}): {len(weak_cids)} control(s) with weak "
                                    f"claim strength ({', '.join(weak_cids[:5])}). Vendor responses lack "
                                    f"sufficient detail or justification."),
                    "severity": "medium",
                    "related_question_id": weak_cids[0],
                    "source_refs": {
                        "questionnaire": weak_cids[:5],
                        "artifacts": [],
                        "policies": [],
                        "contracts": [],
                    },
                    "evidence_assessment": "Weak vendor responses",
                })

        contract_refs = re.findall(r'"category":\s*"([^"]+)"', prompt)
        if contract_refs:
            gaps.append({
                "gap_type": "policy_violation",
                "description": ("Cross-cutting: No penetration test report or vulnerability assessment "
                                "provided despite contractual requirements in " +
                                ", ".join(contract_refs[:3]) + "."),
                "severity": "critical",
                "related_question_id": None,
                "source_refs": {
                    "questionnaire": [], "artifacts": [],
                    "policies": [], "contracts": contract_refs[:3],
                },
                "evidence_assessment": "No penetration test evidence provided",
            })

        fully = sum(1 for s in section_controls if all(
            c in evidenced_controls for c in section_controls[s]))
        partially = sum(1 for s in section_controls if any(
            c in evidenced_controls for c in section_controls[s]) and not all(
            c in evidenced_controls for c in section_controls[s]))
        no_ev = len(section_controls) - fully - partially

        return {
            "total_gaps_found": len(gaps),
            "gaps": gaps,
            "coverage_summary": {
                "fully_evidenced": fully,
                "partially_evidenced": partially,
                "no_evidence": no_ev,
            },
        }

    # ── Risk assessment ──────────────────────────────────
    if "score the following compliance gaps" in sp:
        risk_scores = []
        gap_ids = re.findall(r'"gap_id":\s*"([^"]+)"', prompt)
        levels = ["critical", "high", "high", "medium"]
        rationales = [
            "Missing risk register evidence undermines confidence in vendor's ERM governance program.",
            "Absence of network security documentation poses a significant unassessed risk surface.",
            "Incomplete access reviews leave potential for unauthorized access to sensitive data.",
            "Lack of penetration testing evidence violates contractual requirements; regulatory risk under ISO 27001.",
        ]
        plans = [
            "Request vendor to provide risk register export and board review minutes within 30 days.",
            "Require vendor to submit network architecture diagram and penetration test report.",
            "Vendor must extend access review programme to all SaaS tools within 60 days.",
            "Contract amendment requiring annual penetration test with results shared.",
        ]
        for i, gid in enumerate(gap_ids):
            risk_scores.append({
                "gap_id": gid,
                "risk_level": levels[i % len(levels)],
                "rationale": rationales[i % len(rationales)],
                "regulatory_impact": "ISO 27001, SOC 2" if i % 2 == 0 else "GDPR Article 32",
                "remediation_plan": plans[i % len(plans)],
                "priority": (i % 4) + 1,
            })
        return {
            "risk_scores": risk_scores,
            "overall_risk_rating": "high",
            "executive_summary": "Vendor presents moderate-to-high third-party risk. While stated controls are comprehensive, critical evidence gaps require immediate remediation.",
        }

    # ── Recommendations ──────────────────────────────────
    if "recommend" in sp:
        recs = []
        gap_ids = re.findall(r'"gap_id":\s*"([^"]+)"', prompt)
        # Extract existing clause IDs and content from prompt
        existing_clause_ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
        existing_clause_contents = re.findall(r'"content":\s*"([^"]{10,200})"', prompt)

        new_clause_templates = [
            "Vendor shall maintain and annually update a risk register, providing written evidence upon request.",
            "Vendor shall conduct and share results of annual network penetration tests by a qualified third party.",
            "Vendor shall perform user access reviews covering all systems processing Customer data quarterly.",
            "Vendor shall maintain ISO 27001 or SOC 2 Type II certification and provide certificates within 30 days.",
            "Vendor shall implement and maintain encryption at rest using AES-256 or equivalent for all Customer data.",
            "Vendor shall notify Customer of any security incident within 24 hours of detection.",
            "Vendor shall implement multi-factor authentication for all administrative access to systems processing Customer data.",
            "Vendor shall maintain business continuity and disaster recovery plans, tested annually, with documented results.",
            "Vendor shall ensure all subprocessors meet equivalent security obligations and provide a current list upon request.",
            "Vendor shall retain security logs for a minimum of 12 months and make them available for audit upon request.",
        ]
        for i, gid in enumerate(gap_ids):
            # First recommend from existing clauses if available
            if existing_clause_ids and i < len(existing_clause_ids):
                recs.append({
                    "gap_id": gid,
                    "risk_level": _rng.choice(["high", "medium"]),
                    "recommended_clause": existing_clause_contents[i] if i < len(existing_clause_contents) else f"Existing clause {existing_clause_ids[i]}",
                    "justification": f"This existing contract clause directly addresses the identified gap.",
                    "existing_coverage": "partial",
                    "priority": "must_have" if i < 3 else "should_have",
                    "source": "existing",
                    "source_clause_id": existing_clause_ids[i],
                })
            # Also add a new clause suggestion for each gap
            recs.append({
                "gap_id": gid,
                "risk_level": _rng.choice(["high", "medium", "low"]),
                "recommended_clause": new_clause_templates[i % len(new_clause_templates)],
                "justification": f"New clause to strengthen contractual coverage for this gap area.",
                "existing_coverage": "none",
                "priority": "must_have" if i < 2 else "should_have",
                "source": "new",
                "source_clause_id": None,
            })
        # Future / proactive risk clauses — use existing clauses first where applicable
        future_risk_newclauses = [
            ("Vendor shall comply with all applicable AI governance regulations including the EU AI Act and shall provide transparency reports on any AI/ML systems processing Customer data.",
             "Proactive coverage for emerging AI governance regulations that may affect vendor operations."),
            ("Vendor shall not use Customer data for training machine learning models without prior written consent and shall maintain audit trails of all automated decision-making.",
             "Addresses future risk of unauthorized AI training on sensitive data."),
            ("Vendor shall maintain a documented supply chain security program, including software bill of materials (SBOM) for all components processing Customer data.",
             "Mitigates emerging software supply chain attack risks."),
            ("Vendor shall ensure data residency and sovereignty compliance with all current and foreseeable jurisdictional requirements, providing 90 days advance notice of any data location changes.",
             "Proactive protection against evolving data sovereignty and cross-border transfer regulations."),
            ("Vendor shall provide a documented exit strategy and data portability plan ensuring Customer can migrate all data within 90 days in standard formats upon contract termination.",
             "Addresses vendor lock-in and technology obsolescence risks."),
            ("Vendor shall maintain cyber insurance coverage of no less than $5M per occurrence and provide annual certificate of insurance to Customer.",
             "Financial protection against future large-scale cyber incidents."),
            ("Vendor shall conduct annual third-party security assessments of its own subprocessors and critical suppliers, sharing summary results with Customer.",
             "Addresses fourth-party (Nth party) supply chain risks."),
        ]
        # First, recommend existing clauses that cover future risk areas
        future_keywords = ["data", "security", "audit", "compliance", "subcontract", "subprocessor", "insurance", "incident", "breach", "encrypt", "access", "retention", "privacy"]
        existing_used_for_future = set()
        for ci, clause_content in enumerate(existing_clause_contents):
            clause_lower = clause_content.lower()
            if any(kw in clause_lower for kw in future_keywords) and ci not in existing_used_for_future:
                existing_used_for_future.add(ci)
                recs.append({
                    "gap_id": "FUTURE",
                    "risk_level": _rng.choice(["medium", "high"]),
                    "recommended_clause": clause_content,
                    "justification": "This existing contract clause provides proactive coverage for potential future risks in this domain.",
                    "existing_coverage": "partial",
                    "priority": "should_have",
                    "source": "existing",
                    "source_clause_id": existing_clause_ids[ci] if ci < len(existing_clause_ids) else None,
                })
        # Then add new future risk clauses for areas not covered by existing
        for i, (clause_text, justification) in enumerate(future_risk_newclauses):
            recs.append({
                "gap_id": "FUTURE",
                "risk_level": _rng.choice(["medium", "high"]),
                "recommended_clause": clause_text,
                "justification": justification,
                "existing_coverage": "none",
                "priority": _rng.choice(["should_have", "nice_to_have"]),
                "source": "future_risk",
                "source_clause_id": None,
            })
        return {"recommendations": recs}

    return {"info": "No matching mock for this prompt", "raw_prompt_len": len(prompt)}


# ═══════════════════════════════════════════════════════════════════
#  PROMPT TEMPLATES (self-contained, no dependency on app.utils.prompts)
# ═══════════════════════════════════════════════════════════════════

PROMPT_TEMPLATES = {
    "questionnaire_analysis": {
        "system": "You are an expert TPRM security analyst. You analyze vendor questionnaire responses to identify risk indicators, weak responses, and required evidence. Always respond with valid JSON.",
        "user": """Analyze the following parsed questionnaire data for a vendor named "{{vendor_name}}".

For each question, evaluate:
1. risk_relevance: How relevant is this question to security risk? (high/medium/low/none)
2. claim_strength: How strong is the vendor's claim? (0.0 = very weak, 1.0 = very strong)
3. expected_evidence: What artifacts should the vendor provide to support this response?
4. flags: Any concerns (weak_response, vague_answer, missing_justification, contradictory)

Return JSON with vendor_profile, control_coverage, overall_risk_indicators, and question_analysis array.

PARSED QUESTIONNAIRE DATA:
{{questionnaire_data}}""",
    },
    "artifact_insight": {
        "system": "You are an expert document analyst specializing in security and compliance artifacts. You can analyze documents of any format including text documents, scanned PDFs, and images (certificates, screenshots, compliance dashboards). For image-based artifacts, pay special attention to the filename, any OCR-extracted text, and infer the artifact's purpose from all available context. Always respond with valid JSON.",
        "user": """Analyze the following vendor artifact content and extract security-relevant insights.

Source type: {{source_type}}

IMPORTANT: If this is an image artifact, the content may include OCR-extracted text which could be partial or noisy. Use the filename and any available text to determine what this artifact represents (e.g. a certification, audit report screenshot, compliance dashboard, architecture diagram, etc.). Even partial evidence from images should be captured.

Identify: document_type, policy_coverage, certifications, security_controls, compliance_indicators, key_findings.

Return JSON with document_type, policy_coverage (list of areas covered), certifications (list of any certifications evidenced), security_controls (list of controls demonstrated), compliance_indicators (list of compliance evidence found), key_findings (list of important findings), confidence (high/medium/low).

ARTIFACT CONTENT ({{artifact_name}}):
{{artifact_content}}""",
    },
    "gap_analysis": {
        "system": "You are an expert TPRM gap analyst. You identify compliance gaps by cross-referencing vendor questionnaire responses against artifact evidence, internal policies, and contract clauses. You MUST consider ALL forms of evidence including document artifacts AND image artifacts (certificates, screenshots, compliance dashboards). If an artifact — regardless of format — provides evidence for a claim, that claim is supported and should NOT be flagged as a gap. Always respond with valid JSON.",
        "user": """Perform gap analysis for this vendor assessment.

QUESTIONNAIRE INSIGHTS (what the vendor claims):
{{questionnaire_insights}}

RELEVANT ARTIFACT EVIDENCE — TEXT CHUNKS (RAG-matched evidence from vendor documents and images):
{{artifact_evidence}}

ARTIFACT INSIGHT SUMMARIES (LLM-analyzed summaries of ALL vendor artifacts, including images):
{{artifact_insight_summary}}

IMPORTANT: The artifact insight summaries above contain the analyzed findings from EVERY artifact the vendor provided, including image files (certificates, screenshots, compliance evidence). You MUST cross-reference these summaries when evaluating whether a vendor claim is supported. If an artifact insight summary shows a certification, security control, or compliance indicator that supports a vendor's claim, that claim IS evidenced — do NOT flag it as a gap.

INTERNAL POLICY REQUIREMENTS (what we require):
{{policy_context}}

CONTRACT CLAUSE REQUIREMENTS (what the contract mandates):
{{contract_context}}

For each identified gap, determine the correct gap_type using this decision matrix:

GAP TYPE DECISION MATRIX — YOU MUST USE ALL FOUR TYPES APPROPRIATELY:

1. "missing_artifact" — The vendor was EXPECTED to provide documentation/evidence for a control area (e.g., SOC 2 report, penetration test results, BCP/DR plan, encryption certificates, audit logs) but NO such artifact was provided at all. Use this when the gap is about MISSING DOCUMENTATION, not about what the vendor claimed.

2. "unsupported_claim" — The vendor made a SPECIFIC CLAIM in the questionnaire response (e.g., "We use AES-256 encryption", "We conduct annual pen tests") but the provided artifacts do NOT contain evidence to VERIFY that claim. The difference from missing_artifact: here the vendor claims to have the control but can't prove it.

3. "policy_violation" — The vendor's response or practice DIRECTLY CONTRADICTS or FAILS TO MEET a specific requirement from our INTERNAL POLICY or CONTRACT CLAUSES. For example: our policy requires 90-day password rotation but the vendor states 180 days; our policy requires data stored in-region but the vendor uses multi-region storage; our contract requires annual audits but the vendor only does biennial ones.

4. "control_missing" — The vendor explicitly stated that a security control is NOT IMPLEMENTED, or answered "No" / "Not Applicable" / "N/A" to a question about a required control WITHOUT adequate justification. For example: vendor says "We do not have a formal incident response plan" or responds N/A to questions about access controls.

STEP-BY-STEP TYPE SELECTION — follow this decision tree for EVERY gap, in order:

  STEP 1: Did the vendor explicitly say "No", "N/A", "Not implemented", or leave the response blank (null)?
    → YES → use "control_missing"
    → NO  → continue to STEP 2

  STEP 2: Does the vendor's stated value/practice DIRECTLY contradict a specific, measurable requirement in the INTERNAL POLICY or CONTRACT CLAUSES provided (e.g. policy says 90 days, vendor says 180 days)?
    → YES → use "policy_violation"
    → NO  → continue to STEP 3

  STEP 3: Did the vendor make a SPECIFIC factual claim (e.g. "We use AES-256", "We conduct quarterly pen tests") AND no artifact evidence confirms that specific claim?
    → YES → use "unsupported_claim"
    → NO  → continue to STEP 4

  STEP 4: Did the vendor NOT provide a standard compliance document that would normally be expected (SOC 2, pen test report, BCP/DR plan, ISO certificate) AND no such document exists in the artifacts?
    → YES → use "missing_artifact"
    → NO  → this is likely NOT a gap — do not flag it

COMMON MISCLASSIFICATIONS TO AVOID:
- Vendor says "Yes we have encryption" but no artifact proves it → "unsupported_claim" (NOT "missing_artifact" — the vendor made a specific claim)
- Vendor did not upload a SOC 2 report → "missing_artifact" (NOT "unsupported_claim" — vendor never claimed to have one explicitly)
- Vendor says "We rotate passwords every 6 months" but policy requires 3 months → "policy_violation" (NOT "control_missing" — the control exists, it just violates policy)
- Vendor answered "N/A" to MFA requirement without justification → "control_missing" (NOT "policy_violation" — vendor didn't claim compliance, they denied it)

IMPORTANT: A realistic assessment should include a MIX of these gap types. Do NOT default everything to "unsupported_claim". Carefully evaluate each gap and assign the MOST ACCURATE type.

For each gap, provide:
- gap_type: missing_artifact | unsupported_claim | policy_violation | control_missing
- description: Clear description of the gap (MUST be a non-empty sentence explaining the issue)
- severity: critical | high | medium | low
- related_question_id: The control_id of the related questionnaire question
- source_refs: References to specific questionnaire responses, artifact chunks, or policy sections
- evidence_assessment: What evidence exists (or is missing) — MUST be a non-empty explanation

CRITICAL — QUALITY OVER QUANTITY:
You MUST analyze every questionnaire question, BUT only report gaps that are GENUINELY SIGNIFICANT and clearly evidenced.
- A typical well-managed vendor should have 8–20 gaps. Going above 25 is a red flag that you are being too aggressive.
- Do NOT flag minor or trivial issues. Focus on gaps that would actually concern a risk committee.
- Do NOT report a gap merely because the vendor's answer is brief or generic. Many questionnaire responses are intentionally concise.
- If a vendor says "Yes" to a control and there is no CONTRADICTING evidence, that is NOT a gap.
- If artifacts or insight summaries show the vendor has a control in place, that claim IS supported — do NOT flag it.

CRITICAL — ACCURACY REQUIREMENT (PRECISION FIRST):
Every gap MUST meet a CLEAR EVIDENCE THRESHOLD. Ask yourself: "Can I point to a specific deficiency?" If not, do NOT flag it.
- "unsupported_claim": Only when the vendor makes a SPECIFIC, VERIFIABLE claim (e.g., "We use AES-256", "We do annual pen tests") AND there is genuinely NO artifact evidence to support it. A vendor answering "Yes" to a general question is NOT an unsupported claim — it's a questionnaire response.
- "missing_artifact": Only for CRITICAL documentation that is standard practice to provide (SOC 2 reports, pen test results, BCP plans, certifications). Do NOT flag missing artifacts for every control area.
- "policy_violation": Only when there is a DIRECT, MEASURABLE contradiction (e.g., policy says 90 days but vendor says 180 days). Vague policy language does not create a violation.
- "control_missing": Only when the vendor EXPLICITLY says "No" or "N/A" to a required control WITHOUT adequate justification.

UNANSWERED QUESTIONS (response: null) — MANDATORY RULE:
If a question has "response": null (the vendor did not provide any answer), you MUST treat this as a gap of type "control_missing" UNLESS artifact evidence or insight summaries clearly demonstrate that the control is in place.
Silence is not compliance. An unanswered question on a security control is a strong indicator that the control may not exist or the vendor is unwilling to confirm it.
Do NOT skip unanswered questions — flag each one that lacks supporting artifact evidence.

ERR ON THE SIDE OF CAUTION: False negatives are acceptable. False positives damage credibility. When in doubt, do NOT flag.
However, for unanswered questions specifically, the above caution does NOT apply — treat no response as a gap by default.

Return JSON:
{
  "total_gaps_found": <count>,
  "gaps": [
    {
      "gap_type": "missing_artifact",
      "description": "No SOC 2 Type II report or equivalent audit documentation was provided despite being a standard TPRM requirement",
      "severity": "high",
      "related_question_id": "D.1",
      "source_refs": {
        "questionnaire": ["D.1 - Vendor states SOC 2 audit is conducted annually"],
        "artifacts": [],
        "policies": ["TPRM Policy - Section 3.1 requires independent audit reports"],
        "contracts": []
      },
      "evidence_assessment": "No audit report artifact was provided to verify the claim"
    },
    {
      "gap_type": "unsupported_claim",
      "description": "Vendor claims AES-256 encryption at rest but no artifact provides technical evidence of implementation",
      "severity": "high",
      "related_question_id": "A.5",
      "source_refs": {
        "questionnaire": ["A.5 - Claims AES-256 encryption"],
        "artifacts": [],
        "policies": ["Data Protection Policy - Section 4.2"],
        "contracts": []
      },
      "evidence_assessment": "No supporting artifact found for encryption claim"
    },
    {
      "gap_type": "policy_violation",
      "description": "Vendor password policy requires rotation every 180 days, but our internal policy mandates 90-day rotation",
      "severity": "medium",
      "related_question_id": "B.3",
      "source_refs": {
        "questionnaire": ["B.3 - Vendor states 180-day password rotation"],
        "artifacts": ["InfoSec_Policy.pdf - mentions 180-day cycle"],
        "policies": ["Access Control Policy - Section 2.1 requires 90-day rotation"],
        "contracts": []
      },
      "evidence_assessment": "Vendor policy documented but does not meet our 90-day requirement"
    },
    {
      "gap_type": "control_missing",
      "description": "Vendor explicitly states they do not have a formal data loss prevention (DLP) solution in place",
      "severity": "medium",
      "related_question_id": "C.7",
      "source_refs": {
        "questionnaire": ["C.7 - Vendor responded 'No' to DLP implementation"],
        "artifacts": [],
        "policies": ["Data Protection Policy - Section 5.3 requires DLP controls"],
        "contracts": ["Clause 8.2 - Data protection measures"]
      },
      "evidence_assessment": "Vendor confirmed this control is not implemented"
    }
  ],
  "coverage_summary": {
    "fully_evidenced": <count>,
    "partially_evidenced": <count>,
    "no_evidence": <count>
  }
}""",
    },
    "risk_assessment": {
        "system": "You are an expert risk analyst specializing in third-party risk management. You score compliance gaps based on severity, regulatory impact, evidence quality, and vendor maturity. Always respond with valid JSON.",
        "user": """Score the following compliance gaps identified during a TPRM assessment.

GAPS TO ASSESS:
{{gaps_data}}

VENDOR CONTEXT:
{{vendor_context}}

For each gap, assign:
- risk_level: critical | high | medium | low
- rationale: Detailed explanation of WHY this risk level was assigned (MUST be non-empty)
- regulatory_impact: Any regulatory implications (e.g. GDPR Article 32, ISO 27001, SOC 2)
- remediation_plan: Recommended actions to mitigate the risk
- priority: Suggested remediation priority (1=immediate, 2=short-term, 3=medium-term, 4=long-term)

Return JSON:
{
  "risk_scores": [
    {
      "gap_id": "...",
      "risk_level": "high",
      "rationale": "Missing encryption evidence with regulatory implications under GDPR",
      "regulatory_impact": "GDPR Article 32 - Security of Processing",
      "remediation_plan": "Request vendor to provide encryption implementation documentation",
      "priority": 1
    }
  ],
  "overall_risk_rating": "high",
  "executive_summary": "Brief summary of the vendor's risk posture"
}""",
    },
    "remedial_plan": {
        "system": "You are an expert TPRM remediation consultant. For each compliance gap you create specific, actionable remediation plans with realistic timelines and clear acceptance criteria. Always respond with valid JSON.",
        "user": """You are given a list of compliance gaps of type 'control_missing' or 'policy_violation' identified during a TPRM assessment for vendor "{{vendor_name}}".

These gaps require the vendor to implement or fix specific security controls or policy alignment issues. For EACH gap, create ONE specific, actionable remediation action the vendor must complete.

For each action provide:
- gap_id: The id of the gap this remediates (MUST match exactly from the gaps list below)
- action: A clear, specific action (e.g. "Implement a formal quarterly access review process and document it in the access control policy")
- priority: "immediate" (0–30 days) | "short_term" (30–90 days) | "medium_term" (3–6 months) | "long_term" (6–12 months)
- timeline: Human-readable timeframe (e.g. "Within 30 days", "Within 90 days", "Within 6 months")
- owner: The role responsible (e.g. "Vendor CISO", "Vendor IT Security Team", "Vendor DPO", "Vendor Compliance Team")
- acceptance_criteria: Specific evidence or activity that will confirm this gap is resolved (e.g. "Provide signed access review logs for the past two quarters AND updated access control policy document")

PRIORITY GUIDELINES:
- "immediate": critical severity — poses immediate risk to data security or regulatory compliance
- "short_term": high severity — significant gaps requiring prompt attention
- "medium_term": medium severity — important but less time-sensitive
- "long_term": low severity — process improvements and good-practice items

COMPLIANCE GAPS (control_missing and policy_violation only):
{{gaps_data}}

Return JSON:
{
  "remedial_actions": [
    {
      "gap_id": "exact gap id from gaps list",
      "action": "Specific remediation action the vendor must take",
      "priority": "immediate | short_term | medium_term | long_term",
      "timeline": "Within 30 days",
      "owner": "Vendor IT Security Team",
      "acceptance_criteria": "Specific evidence required to close this item"
    }
  ]
}""",
    },
    "recommendation": {
        "system": "You are a legal and compliance expert specializing in vendor contract clauses for information security and data protection. You must preserve the EXACT original wording of existing contract clauses — do NOT rephrase, summarize, or alter them. Always respond with valid JSON.",
        "user": """You are given a set of identified compliance gaps AND a set of existing contract clauses from the vendor's InfoSec agreement.

Your task is to recommend contract clauses that mitigate EACH identified gap. Follow these rules strictly:

RULE 1 — USE EXISTING CLAUSES FIRST:
For each gap, check if any of the EXISTING CONTRACT CLAUSES below already address or partially address the gap.
If yes, recommend that clause using its EXACT ORIGINAL WORDING — do NOT rephrase, summarize, or modify the text in any way.
Set "source" to "existing" and "source_clause_id" to the clause's id.

RULE 2 — NEW CLAUSES (WHEN GENUINELY NEEDED):
First, always check if any existing clause adequately or partially covers the gap (RULE 1). Existing clauses are strongly preferred.
Only draft a NEW clause when you have reviewed the existing clauses and are confident that none of them sufficiently addresses the gap — i.e. the gap represents a real, material risk that would remain unmitigated without a new clause.
Do NOT draft new clauses simply to be thorough or to add variety. New clauses should be reserved for genuine coverage gaps.
Set "source" to "new" and "source_clause_id" to null.

RULE 3 — FOCUSED COVERAGE:
Generate exactly ONE recommendation per gap. Choose the SINGLE BEST clause (existing or new) that most directly mitigates the gap.
Only generate a SECOND recommendation for a gap if a critical gap genuinely requires both an existing clause reference AND a new clause to fill a remaining gap.
Do NOT pad the output with marginally relevant clauses. Quality over quantity.

RULE 4 — FUTURE / PROACTIVE RISK CLAUSES (EXISTING CLAUSES ONLY):
Beyond the current gaps, identify potential FUTURE risks that could arise from the vendor relationship (e.g. emerging regulatory changes, AI governance, supply chain attacks, data sovereignty shifts, technology obsolescence, vendor lock-in, workforce changes).

CRITICAL: For future risks you MUST ONLY recommend EXISTING contract clauses. Do NOT draft any new clauses for future risks.
  a) Thoroughly scan ALL the EXISTING CONTRACT CLAUSES provided. If ANY existing clause addresses, partially covers, or is relevant to a future risk scenario, recommend that clause using its EXACT ORIGINAL WORDING — do NOT rephrase or modify. Set "source" to "existing", "source_clause_id" to the clause's id, and "existing_coverage" to "partial" or "adequate".
  b) If no existing clause covers a future risk, simply SKIP that risk — do NOT generate a new clause for it.

Set "gap_id" to "FUTURE" for all future risk entries.

IDENTIFIED COMPLIANCE GAPS:
{{gaps_data}}

EXISTING CONTRACT CLAUSES:
{{existing_clauses}}

Return JSON:
{
  "recommendations": [
    {
      "gap_id": "the gap_id this recommendation addresses OR 'FUTURE' for proactive clauses",
      "severity": "critical | high | medium | low",
      "recommended_clause": "The EXACT text of the existing clause OR new clause language",
      "justification": "Why this clause mitigates the identified gap or future risk",
      "existing_coverage": "none | partial | adequate",
      "priority": "must_have | should_have | nice_to_have",
      "source": "existing | new | future_risk",
      "source_clause_id": "id of existing clause or null for new/future suggestions"
    }
  ]
}""",
    },
}


def render_prompt(name: str, **kwargs) -> str:
    """Render a prompt template with provided variables."""
    template = PROMPT_TEMPLATES.get(name)
    if not template:
        raise ValueError(f"Unknown prompt template: {name}")
    user_prompt = template["user"]
    for key, value in kwargs.items():
        user_prompt = user_prompt.replace(f"{{{{{key}}}}}", str(value))
    # Remove any unresolved placeholders (optional params not passed)
    import re as _re
    user_prompt = _re.sub(r"\{\{[a-zA-Z_]+\}\}", "", user_prompt)
    return user_prompt


def get_system_prompt(name: str) -> str:
    """Get the system prompt for a template."""
    template = PROMPT_TEMPLATES.get(name, {})
    return template.get("system", "You are a TPRM security analysis assistant.")


# ═══════════════════════════════════════════════════════════════════
#  CHUNKING (self-contained)
# ═══════════════════════════════════════════════════════════════════

def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[dict]:
    """Split text into overlapping chunks with intelligent boundary detection."""
    if not text or not text.strip():
        return []

    # Normalize whitespace: collapse multiple spaces/tabs to one, strip trailing
    # spaces per line, then collapse 3+ consecutive blank lines to 2.
    import re as _re
    text = _re.sub(r"[ \t]+", " ", text)
    text = _re.sub(r" *\n", "\n", text)
    text = _re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            para_break = text.rfind("\n\n", start + chunk_size // 2, end)
            if para_break != -1:
                end = para_break + 2
            else:
                sentence_break = text.rfind(". ", start + chunk_size // 2, end)
                if sentence_break != -1:
                    end = sentence_break + 2

        chunk_content = text[start:end].strip()
        if chunk_content:
            chunks.append({
                "index": index,
                "content": chunk_content,
                "char_start": start,
                "char_end": end,
            })
            index += 1

        start = end - chunk_overlap
        if start >= len(text):
            break

    return chunks


# ═══════════════════════════════════════════════════════════════════
#  PIPELINE
# ═══════════════════════════════════════════════════════════════════

def run_pipeline(args):
    t0 = time.time()

    print("=" * 70)
    print("  TPRM AI — Assessment Pipeline")
    print("=" * 70)

    # ── Choose real or mock implementations ──────────────
    if args.use_openai:
        from services.embedding_service import openai_embed_text, openai_embed_texts
        logger.info("Using REAL OpenAI API for embeddings and LLM calls")
        embed_fn = openai_embed_text
        embed_batch_fn = openai_embed_texts
        # Use real OpenAI LLM
        from openai import OpenAI
        import os
        import httpx
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""), http_client=httpx.Client(verify=False), base_url="https://ai.titan.in/gateway")

        from services.llm_cache import get_cached, put_cached

        def llm_fn(prompt, system_prompt="", **kw):
            # Check cache first — guarantees deterministic output for same input
            cached = get_cached(prompt, system_prompt)
            if cached is not None:
                return cached

            import time as _time
            model = os.getenv("OPENAI_MODEL", "gpt-5.4-azure")
            for attempt in range(1, 4):
                try:
                    response = _client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0, max_tokens=16384,
                        seed=42,
                        response_format={"type": "json_object"},
                    )
                    content = response.choices[0].message.content
                    if content and content.strip():
                        result = json.loads(content)
                        put_cached(prompt, system_prompt, result)
                        return result
                    logger.warning("Model '%s' empty response (attempt %d)", model, attempt)
                except Exception as e:
                    logger.warning("Model '%s' error (attempt %d): %s", model, attempt, str(e)[:150])
                if attempt < 3:
                    _time.sleep(2 * attempt)
            raise RuntimeError(f"Model '{model}' failed after 3 attempts")
    else:
        logger.info("Using MOCK embeddings and LLM (pass --use-openai for real API)")
        embed_fn = mock_embed_text
        embed_batch_fn = mock_embed_texts
        llm_fn = mock_call_llm_json

    # ── Initialize vector store ──────────────────────────
    vs = JsonVectorStore(VECTOR_STORE_DIR)

    # ── Save helper ──────────────────────────────────────
    def save_output(filename, data, label):
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUTS_DIR / filename
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"     -> Saved to: outputs/{filename}")

    # Resolve input directories
    policy_dir = _find_dir(POLICY_DIRS)
    clause_dir = _find_dir(CLAUSE_DIRS)
    quest_dir = _find_dir(QUESTIONNAIRE_DIRS)

    # ═════════════════════════════════════════════════════
    # STEP 1: Document Ingestion — Parse Questionnaire
    # ═════════════════════════════════════════════════════
    print("\n▶ STEP 1/7: Document Ingestion — Parsing SIG Lite questionnaire")

    q_files = discover_files(quest_dir, {".pdf"})
    questionnaires = []

    for qf in q_files:
        logger.info("Extracting text from %s", qf.name)
        text = extract_text(str(qf))
        if not text.strip():
            logger.warning("No text extracted from %s — skipping", qf.name)
            continue

        parsed = parse_sig_lite_pdf(text)
        logger.info("  Extracted %d questions across %d sections",
                     parsed["total_questions"], len(parsed["sections"]))

        questions = build_questions_with_embeddings(parsed, embed_fn)

        # Analyze questionnaire
        all_control_ids = get_all_control_ids(parsed)
        a_prompt = render_prompt(
            "questionnaire_analysis",
            vendor_name=parsed.get("vendor_name", "Unknown"),
            questionnaire_data=json.dumps(parsed, indent=2)[:15000],
        )
        a_prompt += "\n\n--- ALL CONTROL IDS ---\n" + json.dumps(
            [{"control_id": cid} for cid in all_control_ids]
        )
        a_system = get_system_prompt("questionnaire_analysis")
        analysis = llm_fn(a_prompt, system_prompt=a_system)

        # Apply analysis results to questions
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
            "parsed_content": parsed,
            "analysis_result": analysis,
            "questions": questions,
        })
        logger.info("  Parsed %s: %d questions", qf.name, len(questions))

    # Also load pre-assessment if present
    pre_assessment = None
    if PRE_ASSESSMENT_DIR.exists():
        pa_files = discover_files(PRE_ASSESSMENT_DIR, {".pdf", ".docx", ".txt"})
        for paf in pa_files:
            text = extract_text(str(paf))
            if text.strip():
                pre_assessment = {
                    "file_name": paf.name,
                    "content": text,
                }
                logger.info("Loaded pre-assessment: %s", paf.name)
                break

    total_questions = sum(len(q["questions"]) for q in questionnaires)
    print(f"  ✓ {len(questionnaires)} questionnaire(s), {total_questions} questions parsed")

    save_output("1_questionnaires.json", {
        "step": "1_document_ingestion_questionnaire",
        "total_questionnaires": len(questionnaires),
        "total_questions": total_questions,
        "pre_assessment_loaded": pre_assessment is not None,
        "questionnaires": [
            {
                "id": q["id"],
                "file_name": q["file_name"],
                "vendor_name": q["parsed_content"].get("vendor_name"),
                "parsed_content": q["parsed_content"],
                "analysis_result": q["analysis_result"],
                "questions": q["questions"],
            }
            for q in questionnaires
        ],
    }, "questionnaires")

    # ═════════════════════════════════════════════════════
    # STEP 2: Policy & Clause Embeddings
    # ═════════════════════════════════════════════════════
    print("\n▶ STEP 2/7: Policy & Clause Embeddings")

    policies = process_policies(policy_dir, chunk_text, embed_fn)

    # Store policy vectors
    for p in policies:
        for c in p.get("chunks", []):
            vs.add("policy_vectors", {
                "chunk_id": c["id"],
                "source_document": p["title"],
                "chunk_text": c["content"],
                "embedding": c["embedding"],
            })

    clauses = process_clauses(clause_dir, embed_fn)

    # Store clause vectors
    for cl in clauses:
        vs.add("clause_vectors", {
            "chunk_id": cl["id"],
            "source_document": cl["source_file"],
            "chunk_text": cl["content"],
            "embedding": cl["embedding"],
        })

    total_policy_chunks = sum(len(p.get("chunks", [])) for p in policies)
    print(f"  ✓ {len(policies)} policy/policies ({total_policy_chunks} chunks), {len(clauses)} contract clause(s)")

    save_output("2_policies_and_clauses.json", {
        "step": "2_policy_clause_embeddings",
        "total_policies": len(policies),
        "total_policy_chunks": total_policy_chunks,
        "total_contract_clauses": len(clauses),
        "policies": [
            {
                "id": p["id"],
                "title": p["title"],
                "total_chunks": len(p.get("chunks", [])),
                "chunks": [
                    {
                        "chunk_id": c["id"],
                        "chunk_index": c["chunk_index"],
                        "content": c["content"],
                        "embedding": c["embedding"],
                    }
                    for c in p.get("chunks", [])
                ],
                "file_embedding": p["file_embedding"],
            }
            for p in policies
        ],
        "contract_clauses": [
            {
                "id": cl["id"],
                "source_file": cl["source_file"],
                "category": cl["category"],
                "content": cl["content"],
                "embedding": cl["embedding"],
            }
            for cl in clauses
        ],
    }, "policies & clauses")

    # ═════════════════════════════════════════════════════
    # STEP 3: Questionnaire Analysis (Deep)
    # ═════════════════════════════════════════════════════
    print("\n▶ STEP 3/7: Questionnaire Analysis")

    all_questions = []
    for q in questionnaires:
        all_questions.extend(q["questions"])

    # Identify missing answers, contradictions, unsupported claims
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

    print(f"  ✓ Analysed {len(all_questions)} questions: {len(missing_answers)} missing answers, "
          f"{len(weak_claims)} weak claims, {len(flagged)} flagged")

    save_output("3_questionnaire_analysis.json", {
        "step": "3_questionnaire_analysis",
        **questionnaire_analysis,
    }, "questionnaire analysis")

    # ═════════════════════════════════════════════════════
    # STEP 4: Artifact Analysis
    # ═════════════════════════════════════════════════════
    print("\n▶ STEP 4/7: Artifact Analysis")

    artifacts = process_artifacts(
        ARTIFACT_DIR, chunk_text, embed_fn, embed_batch_fn,
        llm_fn, render_prompt, get_system_prompt,
        max_artifacts=args.max_artifacts,
    )

    # Store artifact vectors
    for art in artifacts:
        for c in art.get("chunks", []):
            vs.add("artifact_vectors", {
                "chunk_id": c["id"],
                "source_document": art["file_name"],
                "chunk_text": c["content"],
                "embedding": c["embedding"],
            })

    total_chunks = sum(len(a.get("chunks", [])) for a in artifacts)
    print(f"  ✓ {len(artifacts)} artifact(s), {total_chunks} chunks embedded")

    save_output("4_artifacts.json", {
        "step": "4_artifact_analysis",
        "total_artifacts": len(artifacts),
        "total_chunks": total_chunks,
        "artifacts": [
            {
                "id": a["id"],
                "file_name": a["file_name"],
                "file_embedding": a["file_embedding"],
                "total_chunks": len(a["chunks"]),
                "chunks": [
                    {
                        "chunk_id": c["id"],
                        "chunk_index": c["chunk_index"],
                        "content": c["content"],
                        "metadata": c["metadata"],
                        "embedding": c["embedding"],
                    }
                    for c in a["chunks"]
                ],
                "insights": a["insights"],
            }
            for a in artifacts
        ],
    }, "artifacts")

    # Save vector stores to disk
    vs.save("policy_vectors")
    vs.save("clause_vectors")
    vs.save("artifact_vectors")
    print(f"  ✓ Vector stores saved: policy({vs.count('policy_vectors')}), "
          f"clause({vs.count('clause_vectors')}), artifact({vs.count('artifact_vectors')})")

    # ═════════════════════════════════════════════════════
    # STEP 5: Risk Assessment (Gap Analysis + Scoring)
    # ═════════════════════════════════════════════════════
    print("\n▶ STEP 5/7: Gap Analysis & Risk Assessment")

    gap_result = run_gap_analysis(
        all_questions, artifacts, policies, clauses,
        embed_fn, llm_fn, render_prompt, get_system_prompt,
    )
    gaps = gap_result["gaps"]

    print(f"  ✓ {len(gaps)} gaps identified")
    for g in gaps:
        print(f"    [{g['severity'].upper():>8s}] {g['gap_type']}: {g['description'][:80]}")

    save_output("5_gap_analysis.json", {
        "step": "5_gap_analysis",
        "total_gaps": len(gaps),
        "security_questions_searched": gap_result["security_questions_searched"],
        "evidence_chunks_matched": gap_result["evidence_chunks_matched"],
        "severity_breakdown": {s: sum(1 for g in gaps if g["severity"] == s)
                               for s in {g["severity"] for g in gaps}},
        "coverage_summary": gap_result["coverage_summary"],
        "gaps": gaps,
        "rag_evidence_sample": gap_result["rag_evidence_sample"],
    }, "gap analysis")

    # Risk scoring
    vendor_name = "Unknown"
    if questionnaires:
        vendor_name = questionnaires[0]["parsed_content"].get("vendor_name", "Unknown")

    risk_result = run_risk_assessment(
        gaps, vendor_name,
        llm_fn, render_prompt, get_system_prompt,
    )
    risks = risk_result["risks"]

    print(f"  ✓ {len(risks)} risks scored")
    for r in risks:
        print(f"    [{r['risk_level'].upper():>8s}] {r['rationale'][:80]}")

    save_output("6_risk_assessment.json", {
        "step": "6_risk_assessment",
        "total_risks": len(risks),
        "overall_risk_rating": risk_result["overall_risk_rating"],
        "executive_summary": risk_result["executive_summary"],
        "level_breakdown": {lvl: sum(1 for r in risks if r["risk_level"] == lvl)
                           for lvl in {r["risk_level"] for r in risks}},
        "risks": risks,
    }, "risk assessment")

    # ═════════════════════════════════════════════════════
    # STEP 6: Clause Recommendations
    # ═════════════════════════════════════════════════════
    print("\n▶ STEP 6/7: Clause Recommendations")

    recommendations = run_recommendations(
        gaps, risks, clauses,
        embed_fn, llm_fn, render_prompt, get_system_prompt,
    )

    print(f"  ✓ {len(recommendations)} recommendations generated")

    save_output("7_recommendations.json", {
        "step": "7_clause_recommendations",
        "total_recommendations": len(recommendations),
        "priority_breakdown": {p: sum(1 for r in recommendations if r.get("priority") == p)
                              for p in {r.get("priority") for r in recommendations}},
        "recommendations": recommendations,
    }, "recommendations")

    # ═════════════════════════════════════════════════════
    # STEP 7: Reasoning & Final Assessment
    # ═════════════════════════════════════════════════════
    print("\n▶ STEP 7/7: Reasoning & Final Assessment Report")

    elapsed = time.time() - t0

    # ── Compliance areas analysis ────────────────────────
    compliant_areas = []
    partially_compliant = []
    non_compliant = []
    missing_controls = []

    gap_sections = set()
    for g in gaps:
        refs = g.get("source_refs", {})
        for cid in refs.get("questionnaire", []):
            sec = cid.split(".")[0] if "." in cid else ""
            gap_sections.add(sec)
        if g["severity"] == "critical":
            non_compliant.append(g["description"][:120])
        elif g["severity"] == "high":
            partially_compliant.append(g["description"][:120])
        if g["gap_type"] == "missing_artifact":
            missing_controls.append(g["description"][:120])

    # Sections without gaps
    all_sections = set()
    for q in all_questions:
        sec = q.get("control_id", "").split(".")[0] if q.get("control_id") else ""
        if sec:
            all_sections.add(sec)
    compliant_sections = all_sections - gap_sections
    for s in sorted(compliant_sections):
        compliant_areas.append(f"Section {s}: No gaps identified")
    non_compliant.sort()
    partially_compliant.sort()
    missing_controls.sort()

    # ── Build final report ───────────────────────────────
    report = {
        "pipeline_mode": "mock" if not args.use_openai else "openai",
        "elapsed_seconds": round(elapsed, 2),
        "input_summary": {
            "questionnaires": len(questionnaires),
            "total_questions": total_questions,
            "artifacts": len(artifacts),
            "total_chunks": total_chunks,
            "policies": len(policies),
            "contract_clauses": len(clauses),
            "pre_assessment_loaded": pre_assessment is not None,
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
            "overall": risk_result["overall_risk_rating"],
            "breakdown": {lvl: sum(1 for r in risks if r["risk_level"] == lvl)
                         for lvl in {r["risk_level"] for r in risks}},
        },
        "recommended_clauses": [
            {
                "clause": rec["clause_text"],
                "justification": rec["justification"],
                "priority": rec.get("priority"),
                "existing_coverage": rec.get("existing_coverage"),
            }
            for rec in recommendations
        ],
        "gaps": gaps,
        "risks": risks,
        "recommendations": recommendations,
        "summary": {
            "total_gaps": len(gaps),
            "total_risks": len(risks),
            "total_recommendations": len(recommendations),
            "gap_severity": {s: sum(1 for g in gaps if g["severity"] == s)
                            for s in {g["severity"] for g in gaps}},
            "risk_levels": {lvl: sum(1 for r in risks if r["risk_level"] == lvl)
                           for lvl in {r["risk_level"] for r in risks}},
            "overall_risk_rating": risk_result["overall_risk_rating"],
            "executive_summary": risk_result["executive_summary"],
        },
    }

    # Save JSON report
    save_output("assessment_report.json", report, "final report")

    # ── Generate Markdown summary ────────────────────────
    md = _generate_markdown_summary(report, gaps, risks, recommendations, vendor_name, elapsed)
    md_path = OUTPUTS_DIR / "assessment_summary.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"     -> Saved to: outputs/assessment_summary.md")

    # ── Print final summary ──────────────────────────────
    print("\n" + "=" * 70)
    print("  TPRM ASSESSMENT REPORT — SUMMARY")
    print("=" * 70)
    print(f"  Mode:             {'MOCK' if not args.use_openai else 'OPENAI'}")
    print(f"  Elapsed:          {elapsed:.1f}s")
    print(f"  Questionnaires:   {len(questionnaires)}")
    print(f"  Total Questions:  {total_questions}")
    print(f"  Artifacts:        {len(artifacts)} ({total_chunks} chunks)")
    print(f"  Policies:         {len(policies)}")
    print(f"  Contract Clauses: {len(clauses)}")
    print(f"\n--- Gaps: {len(gaps)} total ---")
    for sev, cnt in sorted(report["summary"]["gap_severity"].items()):
        print(f"  {sev:>10s}: {cnt}")
    print(f"\n--- Risks: {len(risks)} total ---")
    print(f"  Overall Rating: {report['summary']['overall_risk_rating']}")
    for lvl, cnt in sorted(report["summary"]["risk_levels"].items()):
        print(f"  {lvl:>10s}: {cnt}")
    if report["summary"]["executive_summary"]:
        print(f"\n--- Executive Summary ---")
        print(f"  {report['summary']['executive_summary']}")
    print(f"\n--- Recommendations: {len(recommendations)} ---")
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. [{rec.get('priority', 'N/A')}] {rec['clause_text'][:100]}")

    print(f"\n  Output files:")
    print(f"    1. outputs/1_questionnaires.json          - Parsed questions & analysis")
    print(f"    2. outputs/2_policies_and_clauses.json    - Policy/clause embeddings")
    print(f"    3. outputs/3_questionnaire_analysis.json  - Questionnaire deep analysis")
    print(f"    4. outputs/4_artifacts.json               - Artifact chunks & insights")
    print(f"    5. outputs/5_gap_analysis.json            - Identified gaps")
    print(f"    6. outputs/6_risk_assessment.json         - Scored risks")
    print(f"    7. outputs/7_recommendations.json         - Clause recommendations")
    print(f"    8. outputs/assessment_report.json         - Full assessment report")
    print(f"    9. outputs/assessment_summary.md          - Human-readable summary")
    print(f"\n  Vector stores:")
    print(f"    vector_store/policy_vectors.json   ({vs.count('policy_vectors')} entries)")
    print(f"    vector_store/clause_vectors.json   ({vs.count('clause_vectors')} entries)")
    print(f"    vector_store/artifact_vectors.json ({vs.count('artifact_vectors')} entries)")
    print("=" * 70)


def _generate_markdown_summary(report, gaps, risks, recommendations, vendor_name, elapsed):
    """Generate a human-readable Markdown summary."""
    lines = [
        f"# TPRM Assessment Report — {vendor_name}",
        "",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Mode:** {report['pipeline_mode']}",
        f"**Processing time:** {elapsed:.1f}s",
        "",
        "---",
        "",
        "## Input Summary",
        "",
        f"| Input | Count |",
        f"|---|---|",
        f"| Questionnaires | {report['input_summary']['questionnaires']} |",
        f"| Total Questions | {report['input_summary']['total_questions']} |",
        f"| Artifacts | {report['input_summary']['artifacts']} |",
        f"| Artifact Chunks | {report['input_summary']['total_chunks']} |",
        f"| Policies | {report['input_summary']['policies']} |",
        f"| Contract Clauses | {report['input_summary']['contract_clauses']} |",
        "",
        "---",
        "",
        "## Questionnaire Findings",
        "",
        f"- **Vendor:** {vendor_name}",
        f"- **Missing answers:** {report['questionnaire_findings']['missing_answers']}",
        f"- **Weak claims:** {report['questionnaire_findings']['weak_claims']}",
        f"- **Flagged questions:** {report['questionnaire_findings']['flagged_questions']}",
        "",
        "---",
        "",
        "## Risk Rating",
        "",
        f"**Overall: {report['risk_rating']['overall'].upper()}**",
        "",
        "| Level | Count |",
        "|---|---|",
    ]
    for lvl, cnt in sorted(report["risk_rating"]["breakdown"].items()):
        lines.append(f"| {lvl} | {cnt} |")

    lines += [
        "",
        "---",
        "",
        "## Gaps Identified",
        "",
        f"**Total: {len(gaps)}**",
        "",
    ]
    for i, g in enumerate(gaps, 1):
        lines.append(f"### {i}. [{g['severity'].upper()}] {g['gap_type']}")
        lines.append(f"")
        lines.append(f"{g['description']}")
        lines.append(f"")
        if g.get("evidence_assessment"):
            lines.append(f"**Evidence:** {g['evidence_assessment']}")
            lines.append(f"")

    lines += [
        "---",
        "",
        "## Recommended Contract Clauses",
        "",
    ]
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"### {i}. [{rec.get('priority', 'N/A').upper()}]")
        lines.append(f"")
        lines.append(f"> {rec['clause_text']}")
        lines.append(f"")
        lines.append(f"**Justification:** {rec['justification']}")
        lines.append(f"")

    lines += [
        "---",
        "",
        "## Executive Summary",
        "",
        report["summary"].get("executive_summary", "N/A"),
        "",
        "---",
        "",
        "## Policy Compliance",
        "",
    ]
    if report["policy_compliance"]["compliant_areas"]:
        lines.append("### Compliant Areas")
        for area in report["policy_compliance"]["compliant_areas"]:
            lines.append(f"- ✅ {area}")
        lines.append("")
    if report["policy_compliance"]["partially_compliant"]:
        lines.append("### Partially Compliant")
        for area in report["policy_compliance"]["partially_compliant"]:
            lines.append(f"- ⚠️ {area}")
        lines.append("")
    if report["policy_compliance"]["non_compliant"]:
        lines.append("### Non-Compliant")
        for area in report["policy_compliance"]["non_compliant"]:
            lines.append(f"- ❌ {area}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Run the TPRM AI assessment pipeline",
    )
    parser.add_argument(
        "--use-openai",
        action="store_true",
        help="Use real OpenAI API instead of mock responses",
    )
    parser.add_argument(
        "--max-artifacts",
        type=int,
        default=None,
        help="Limit the number of artifacts to process (default: all)",
    )
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
