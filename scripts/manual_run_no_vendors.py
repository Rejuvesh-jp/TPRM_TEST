"""
Vendor-Free Local TPRM Analysis Pipeline
=========================================
Runs the entire TPRM AI assessment pipeline offline using folder-based inputs.
No HTTP server, no database, no vendor management needed.

Inputs (place files in these folders):
    ./inputs/questionnaires/   - SIG Lite PDFs
    ./inputs/artifacts/        - PDF/DOCX/TXT/CSV/XLSX/JSON
    ./inputs/policies/         - PDF/TXT
    ./inputs/contract_clauses/ - PDF/DOCX/TXT

Usage:
    python scripts/manual_run_no_vendors.py
    python scripts/manual_run_no_vendors.py --use-openai   # use real OpenAI API
    python scripts/manual_run_no_vendors.py --max-artifacts 5
"""

import argparse
import hashlib
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

# ── Fix Windows console encoding (cp1252 → utf-8) ───────────────────
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Project root on sys.path ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.extraction import extract_text, EXTRACTORS
from app.utils.chunking import chunk_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tprm.local_pipeline")

INPUTS_DIR = PROJECT_ROOT / "inputs"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ═══════════════════════════════════════════════════════════════════
#  SIG LITE PDF PARSER (extracts ALL questions section-wise)
# ═══════════════════════════════════════════════════════════════════

# Section-number → (letter, full_name)  for SIG Lite
SIG_SECTION_MAP = {
    1: ("BI", "Business Information"),
    2: ("DRL", "Document Request List"),
    3: ("A", "A. Enterprise Risk Management"),
    4: ("B", "B. Nth Party Management"),
    5: ("C", "C. Information Assurance"),
    6: ("D", "D. Asset and Info Management"),
    7: ("E", "E. Human Resources Security"),
    8: ("F", "F. Physical and Environmental Security"),
    9: ("G", "G. IT Operations Management"),
    10: ("H", "H. Access Control"),
    11: ("I", "I. Application Security"),
    12: ("J", "J. Cybersecurity Incident Mgmt."),
    13: ("K", "K. Operational Resilience"),
    14: ("L", "L. Compliance Management"),
    15: ("M", "M. Endpoint Security"),
    16: ("N", "N. Network Security"),
    17: ("O", "O. Environmental, Social and Governance (ESG)"),
    18: ("P", "P. Privacy Management"),
    19: ("T", "T. Threat Management"),
    20: ("U", "U. Server Security"),
    21: ("V", "V. Cloud Hosting Services"),
}


def parse_sig_lite_pdf(text: str) -> dict:
    """Parse SIG Lite questionnaire text extracting ALL questions with
    their responses and justifications, organised by section."""

    # Dynamically discover section headers from the text
    # Pattern: \n<num>\n<num>\n<Letter>. <Name>
    discovered = {}
    for m in re.finditer(r'\n(\d+)\n\d+\n([A-Z])\.\s+([^\n]+)', text):
        num = int(m.group(1))
        letter = m.group(2)
        name = m.group(3).strip()
        discovered[num] = (letter, f"{letter}. {name}")

    section_map = dict(SIG_SECTION_MAP)
    section_map.update(discovered)

    # Split into question blocks — each starts with <sec_num>.<sub_num>\n
    question_re = re.compile(r'(?:^|\n)(\d+)\.(\d+)\n', re.MULTILINE)
    matches = list(question_re.finditer(text))

    sections_dict = {}  # section_name -> [question, ...]
    vendor_name = None

    for idx, m in enumerate(matches):
        sec_num = int(m.group(1))
        sub_num = int(m.group(2))
        qid_raw = f"{sec_num}.{sub_num}"

        # Extract the text block between this match and the next
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()

        # Remove page markers
        block = re.sub(r'\[Page \d+\]\s*', '', block)

        # Extract question text (first meaningful line, often duplicated)
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue

        # De-duplicate repeated lines at start (PDF extraction artifact)
        question_text = lines[0]

        # Extract response and justification
        response_text = None
        justification = None

        # Look for "Response\nResponse\n<value>" pattern
        resp_match = re.search(r'Response\s*\nResponse\s*\n(.*?)(?=\nJustification|\nAssessment|\Z)',
                               block, re.DOTALL | re.IGNORECASE)
        if resp_match:
            response_text = resp_match.group(1).strip()
            # Clean duplicate lines from response
            resp_lines = response_text.split('\n')
            cleaned = []
            prev = None
            for rl in resp_lines:
                rl = rl.strip()
                if rl and rl != prev:
                    cleaned.append(rl)
                prev = rl
            response_text = ' '.join(cleaned) if cleaned else None

        just_match = re.search(r'Justification\s*\nJustification\s*\n(.*?)(?=\n\d+\.\d+|\Z)',
                               block, re.DOTALL | re.IGNORECASE)
        if just_match:
            justification = just_match.group(1).strip()
            # De-duplicate
            just_lines = justification.split('\n')
            cleaned = []
            prev = None
            for jl in just_lines:
                jl = jl.strip()
                if jl and jl != prev:
                    cleaned.append(jl)
                prev = jl
            justification = ' '.join(cleaned) if cleaned else None

        # Map to section
        sec_info = section_map.get(sec_num, ("?", f"Section {sec_num}"))
        section_name = sec_info[1]
        section_letter = sec_info[0]

        # Build control_id in SIG format
        control_id = f"{section_letter}.{sub_num}" if section_letter not in ("?",) else qid_raw

        # Detect vendor name from Q1.1
        if sec_num == 1 and sub_num == 1 and response_text:
            parts = response_text.split('|')
            vendor_name = parts[0].strip() if parts else response_text[:50]

        if section_name not in sections_dict:
            sections_dict[section_name] = []

        sections_dict[section_name].append({
            "control_id": control_id,
            "question_text": question_text[:500],
            "response_text": response_text,
            "justification": justification,
        })

    # Build ordered sections list
    ordered_sections = []
    for sec_num in sorted(section_map.keys()):
        sec_name = section_map[sec_num][1]
        if sec_name in sections_dict:
            ordered_sections.append({
                "name": sec_name,
                "questions": sections_dict[sec_name],
            })

    # Handle any unmapped sections
    for sec_name, qs in sections_dict.items():
        if sec_name not in [s["name"] for s in ordered_sections]:
            ordered_sections.append({"name": sec_name, "questions": qs})

    total = sum(len(s["questions"]) for s in ordered_sections)

    return {
        "vendor_name": vendor_name or "Unknown Vendor",
        "questionnaire_type": "SIG Lite",
        "total_questions": total,
        "sections": ordered_sections,
    }


# ═══════════════════════════════════════════════════════════════════
#  MOCK IMPLEMENTATIONS (used when --use-openai is not set)
# ═══════════════════════════════════════════════════════════════════

EMBEDDING_DIM = 1536


def _deterministic_embedding(text: str) -> list[float]:
    """Generate a deterministic pseudo-embedding from text content.
    Uses SHA-256 hash seeded PRNG so the same text always produces the
    same vector, making cosine similarity meaningful for identical/similar
    chunks."""
    seed = int(hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]  # unit vector


def mock_embed_text(text: str) -> list[float]:
    return _deterministic_embedding(text[:2000])


def mock_embed_texts(texts: list[str]) -> list[list[float]]:
    return [mock_embed_text(t) for t in texts]


def mock_call_llm_json(prompt: str, system_prompt: str = "", **kw) -> dict:
    """Return plausible mock LLM output based on which prompt template is
    being used (detected from the prompt/system content)."""
    _rng = random.Random(42)

    sp = (system_prompt + " " + prompt).lower()

    # ── Questionnaire parsing — NOT USED (real parser handles this) ───
    if "parse the following sig lite" in sp or "questionnaire text:" in sp:
        # Fall through — real parser (parse_sig_lite_pdf) is used instead.
        return {"vendor_name": "Adobe", "questionnaire_type": "SIG Lite",
                "total_questions": 0, "sections": []}

    # ── Questionnaire analysis — dynamically analyse ALL parsed questions ─
    if "analyze the following parsed questionnaire" in sp:
        # Extract all control_ids from the JSON in the prompt
        control_ids = re.findall(r'"control_id":\s*"([^"]+)"', prompt)

        # Risk-relevant SIG sections (security/compliance domains)
        HIGH_RISK_SECTIONS = {"A", "B", "C", "D", "F", "G", "H", "I", "J",
                              "K", "L", "M", "N", "P", "T", "U", "V"}
        MEDIUM_SECTIONS = {"E", "O"}
        INFO_SECTIONS = {"BI", "DRL"}

        question_analysis = []
        control_coverage = {}

        for cid in control_ids:
            section_letter = cid.split(".")[0] if "." in cid else "?"
            # Determine risk relevance
            if section_letter in HIGH_RISK_SECTIONS:
                risk = _rng.choice(["high", "critical", "high", "high"])
                strength = round(_rng.uniform(0.6, 0.95), 2)
                flags = []
                if strength < 0.7:
                    flags.append("weak_response")
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

            # Track coverage per section
            sec_name = section_letter
            if sec_name not in control_coverage:
                control_coverage[sec_name] = coverage

        return {
            "vendor_profile": "Adobe demonstrates a mature security posture with ISO 27001 alignment. Assessment covers all SIG Lite domains.",
            "control_coverage": control_coverage,
            "overall_risk_indicators": [
                "Partial access reviews may leave ungoverned SaaS accounts",
                "No evidence of regular third-party penetration testing mentioned",
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

    # ── Gap analysis — dynamic based on actual questions & evidence ────
    if "perform gap analysis" in sp:
        # Extract questions from the prompt to build realistic gaps
        control_ids = re.findall(r'"control_id":\s*"([^"]+)"', prompt)
        # Extract risk_relevance per control
        risk_map = {}
        for m in re.finditer(r'"control_id":\s*"([^"]+)".*?"risk_relevance":\s*"([^"]*)"', prompt, re.DOTALL):
            risk_map[m.group(1)] = m.group(2)
        # Extract claim_strength per control
        strength_map = {}
        for m in re.finditer(r'"control_id":\s*"([^"]+)".*?"claim_strength":\s*([\d.]+)', prompt, re.DOTALL):
            strength_map[m.group(1)] = float(m.group(2))
        # Detect which artifact evidence was found
        evidence_chunks = re.findall(r'"matched_question":\s*"([^"]+)"', prompt)
        evidenced_controls = set(evidence_chunks)

        # Categorise and build gaps per SIG security section
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
        gap_types = ["unsupported_claim", "missing_artifact", "weak_evidence",
                      "policy_violation", "incomplete_coverage"]
        severity_levels = ["low", "medium", "high", "critical"]

        # Group controls by section letter
        section_controls = {}
        for cid in control_ids:
            sec = cid.split(".")[0] if "." in cid else cid
            if sec in SIG_SECTIONS:
                section_controls.setdefault(sec, []).append(cid)

        for sec_letter in sorted(section_controls.keys()):
            sec_cids = section_controls[sec_letter]
            sec_name = SIG_SECTIONS.get(sec_letter, sec_letter)

            # Count how many have strong/weak evidence
            has_evidence = sum(1 for c in sec_cids if c in evidenced_controls)
            total = len(sec_cids)

            # Determine gap type and severity based on analysis
            high_risk_cids = [c for c in sec_cids if risk_map.get(c) in ("high", "critical")]
            weak_cids = [c for c in sec_cids if strength_map.get(c, 1.0) < 0.7]

            # Generate gap if there are issues
            if high_risk_cids and has_evidence < total:
                # High-risk questions without full evidence coverage
                gap_type = _rng.choice(["missing_artifact", "unsupported_claim", "weak_evidence"])
                severity = "critical" if len(high_risk_cids) >= 2 else "high"
                desc = (f"Section {sec_letter} ({sec_name}): {len(high_risk_cids)} high/critical-risk "
                        f"control(s) ({', '.join(high_risk_cids[:5])}) lack sufficient artifact evidence. "
                        f"Only {has_evidence}/{total} controls have matching documentation.")
                gaps.append({
                    "gap_type": gap_type,
                    "description": desc,
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
                # Weak responses in this section
                gap_type = "weak_evidence"
                severity = "medium"
                desc = (f"Section {sec_letter} ({sec_name}): {len(weak_cids)} control(s) with weak "
                        f"claim strength ({', '.join(weak_cids[:5])}). Vendor responses lack sufficient "
                        f"detail or justification.")
                gaps.append({
                    "gap_type": gap_type,
                    "description": desc,
                    "severity": severity,
                    "related_question_id": weak_cids[0],
                    "source_refs": {
                        "questionnaire": weak_cids[:5],
                        "artifacts": [],
                        "policies": [],
                        "contracts": [],
                    },
                    "evidence_assessment": "Weak vendor responses",
                })

        # Add cross-cutting policy gap if contract clauses exist
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
                    "questionnaire": [],
                    "artifacts": [],
                    "policies": [],
                    "contracts": contract_refs[:3],
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
        # Parse gap_ids from the prompt to create matching risk scores
        risk_scores = []
        gap_ids = re.findall(r'"gap_id":\s*"([^"]+)"', prompt)

        levels = ["critical", "high", "high", "medium"]
        rationales = [
            "Missing risk register evidence undermines confidence in vendor's ERM governance program.",
            "Absence of network security documentation (pen test, architecture diagrams) poses a significant unassessed risk surface.",
            "Incomplete access reviews leave potential for unauthorized access to sensitive data in ungoverned SaaS applications.",
            "Lack of penetration testing evidence violates contractual requirements and internal policy; regulatory risk under ISO 27001 A.12.6.",
        ]
        plans = [
            "Request vendor to provide risk register export and most recent board review minutes within 30 days.",
            "Require vendor to submit network architecture diagram and most recent penetration test report.",
            "Vendor must extend access review programme to all SaaS tools and provide evidence within 60 days.",
            "Contract amendment requiring annual penetration test with results shared; add SLA for remediation of critical findings.",
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
            "executive_summary": "Adobe presents moderate-to-high third-party risk. While stated controls are comprehensive, critical evidence gaps in penetration testing and access reviews require immediate remediation.",
        }

    # ── Recommendations ──────────────────────────────────
    if "recommend specific contract clauses" in sp or "recommend" in sp:
        recs = []
        gap_ids = re.findall(r'"gap_id":\s*"([^"]+)"', prompt)

        clauses = [
            ("Vendor shall maintain and annually update a risk register, providing written evidence to Customer upon request.",
             "Addresses gap in risk governance documentation."),
            ("Vendor shall conduct and share results of annual network penetration tests performed by a qualified third party.",
             "Mitigates unassessed network attack surface risk."),
            ("Vendor shall perform user access reviews covering all systems processing Customer data at a minimum quarterly frequency.",
             "Closes the partial access review coverage gap reported by the vendor."),
            ("Vendor shall maintain ISO 27001 or SOC 2 Type II certification and provide renewed certificates within 30 days of issuance.",
             "Ensures ongoing compliance assurance through independent audits."),
        ]

        for i, gid in enumerate(gap_ids):
            clause_text, justification = clauses[i % len(clauses)]
            recs.append({
                "gap_id": gid,
                "risk_level": "high",
                "recommended_clause": clause_text,
                "justification": justification,
                "existing_coverage": "none" if i % 3 == 0 else "partial",
                "priority": "must_have" if i < 2 else "should_have",
            })

        return {"recommendations": recs}

    # ── Fallback ─────────────────────────────────────────
    return {"info": "No matching mock for this prompt", "raw_prompt_len": len(prompt)}


# ═══════════════════════════════════════════════════════════════════
#  COSINE SIMILARITY  (same as retrieval_service.py)
# ═══════════════════════════════════════════════════════════════════

def cosine_similarity(a, b):
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def similarity_search(query_embedding, records, embedding_key="embedding", top_k=5):
    """Rank records by cosine similarity to query_embedding, return top_k."""
    scored = []
    for rec in records:
        emb = rec.get(embedding_key)
        if emb is None:
            continue
        sim = cosine_similarity(query_embedding, emb)
        scored.append((sim, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(sim, r) for sim, r in scored[:top_k]]


# ═══════════════════════════════════════════════════════════════════
#  PIPELINE
# ═══════════════════════════════════════════════════════════════════

def discover_files(folder: Path, extensions: set[str] | None = None) -> list[Path]:
    """List files in folder matching given extensions (case-insensitive)."""
    if not folder.exists():
        return []
    files = sorted(f for f in folder.iterdir() if f.is_file())
    if extensions:
        files = [f for f in files if f.suffix.lower() in extensions]
    return files


def run_pipeline(args):
    # ── Choose real or mock implementations ──────────────
    if args.use_openai:
        from app.services.embedding_service import embed_text, embed_texts
        from app.utils.llm import call_llm_json
        logger.info("Using REAL OpenAI API for embeddings and LLM calls")
        _embed_text = embed_text
        _embed_texts = embed_texts
        _call_llm_json = call_llm_json
    else:
        logger.info("Using MOCK embeddings and LLM calls (pass --use-openai for real API)")
        _embed_text = mock_embed_text
        _embed_texts = mock_embed_texts
        _call_llm_json = mock_call_llm_json

    from app.utils.prompts import render_prompt, get_system_prompt

    # ── Helper: save stage output ──────────────────────────
    def _save_stage(filename, data, label):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / filename
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"     -> Saved to: output/{filename}")

    # ── In-memory stores (simulate DB tables) ────────────
    store = {
        "questionnaires": [],   # [{id, file_name, parsed_content, analysis_result, questions}]
        "artifacts": [],        # [{id, file_name, chunks, insights}]
        "policies": [],         # [{id, title, content, embedding}]
        "contract_clauses": [], # [{id, category, content, embedding}]
        "gaps": [],             # [{id, ...gap fields...}]
        "risks": [],            # [{id, gap_id, ...risk fields...}]
        "recommendations": [],  # [{id, risk_id, ...rec fields...}]
    }

    print("=" * 70)
    print("  TPRM AI — Vendor-Free Local Analysis Pipeline")
    print("=" * 70)
    t0 = time.time()

    # ─────────────────────────────────────────────────────
    # STEP 1: Parse questionnaires
    # ─────────────────────────────────────────────────────
    print("\n▶ STEP 1/6: Parsing questionnaires")
    q_files = discover_files(INPUTS_DIR / "questionnaires", {".pdf"})
    logger.info("Found %d questionnaire file(s)", len(q_files))

    for qf in q_files:
        logger.info("Extracting text from %s", qf.name)
        text = extract_text(str(qf))
        if not text.strip():
            logger.warning("No text extracted from %s — skipping", qf.name)
            continue

        # Parse ALL questions directly from the PDF text
        parsed = parse_sig_lite_pdf(text)
        logger.info("  Real parser extracted %d questions across %d sections",
                     parsed["total_questions"], len(parsed["sections"]))

        # Build questions list
        questions = []
        for section in parsed.get("sections", []):
            for q in section.get("questions", []):
                # Separate embeddings for question and response
                q_text = q.get("question_text", "")
                question_embedding = _embed_text(q_text) if q_text.strip() else None

                resp_parts = []
                if q.get("response_text"):
                    resp_parts.append(q["response_text"])
                if q.get("justification"):
                    resp_parts.append(q["justification"])
                resp_text = " | ".join(resp_parts)
                response_embedding = _embed_text(resp_text) if resp_text.strip() else None

                questions.append({
                    "id": str(uuid.uuid4()),
                    "section": section.get("name", "Unknown"),
                    "control_id": q.get("control_id"),
                    "question_text": q_text,
                    "response_text": q.get("response_text"),
                    "justification": q.get("justification"),
                    "question_embedding": question_embedding,
                    "response_embedding": response_embedding,
                    "risk_relevance": None,
                    "claim_strength": None,
                    "expected_evidence": None,
                    "flags": None,
                })

        # Analyze questionnaire
        vendor_name = parsed.get("vendor_name") or "Unknown Vendor"

        # Pass ALL control_ids directly so the mock analyser sees every question
        all_control_ids = []
        for section in parsed.get("sections", []):
            for q in section.get("questions", []):
                all_control_ids.append(q.get("control_id", ""))

        a_prompt = render_prompt(
            "questionnaire_analysis",
            vendor_name=vendor_name,
            questionnaire_data=json.dumps(parsed, indent=2)[:15000],
        )
        # Append full control_id list so the mock can see ALL of them
        a_prompt += "\n\n--- ALL CONTROL IDS ---\n" + json.dumps(
            [{"control_id": cid} for cid in all_control_ids]
        )
        a_system = get_system_prompt("questionnaire_analysis")
        analysis = _call_llm_json(a_prompt, system_prompt=a_system)

        # Update questions with analysis results
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

        entry = {
            "id": str(uuid.uuid4()),
            "file_name": qf.name,
            "parsed_content": parsed,
            "analysis_result": analysis,
            "questions": questions,
        }
        store["questionnaires"].append(entry)
        logger.info("  Parsed %s: %d questions", qf.name, len(questions))

    total_questions = sum(len(q["questions"]) for q in store["questionnaires"])
    print(f"  ✓ {len(store['questionnaires'])} questionnaire(s), {total_questions} questions parsed")

    # Save Step 1 output
    _save_stage("1_questionnaires.json", {
        "step": "1_questionnaire_parsing_and_analysis",
        "total_questionnaires": len(store["questionnaires"]),
        "total_questions": total_questions,
        "questionnaires": [
            {
                "id": q["id"],
                "file_name": q["file_name"],
                "vendor_name": q["parsed_content"].get("vendor_name"),
                "parsed_content": q["parsed_content"],
                "analysis_result": q["analysis_result"],
                "questions": q["questions"],
            }
            for q in store["questionnaires"]
        ],
    }, "questionnaires")

    # ─────────────────────────────────────────────────────
    # STEP 2: Process artifacts
    # ─────────────────────────────────────────────────────
    print("\n▶ STEP 2/6: Processing artifacts")
    a_files = discover_files(
        INPUTS_DIR / "artifacts",
        set(EXTRACTORS.keys()),
    )
    if args.max_artifacts and len(a_files) > args.max_artifacts:
        logger.info("Limiting to %d artifacts (of %d)", args.max_artifacts, len(a_files))
        a_files = a_files[: args.max_artifacts]

    logger.info("Found %d artifact file(s)", len(a_files))
    total_chunks = 0

    for af in a_files:
        logger.info("Processing artifact: %s", af.name)
        try:
            text = extract_text(str(af))
        except Exception as exc:
            logger.warning("  Could not extract text from %s: %s — skipping", af.name, exc)
            continue

        if not text.strip():
            logger.warning("  No text in %s — skipping", af.name)
            continue

        # Chunk
        chunks_raw = chunk_text(text)
        chunk_texts = [c["content"] for c in chunks_raw]

        # Embed
        embeddings = _embed_texts(chunk_texts)

        chunks = []
        for cd, emb in zip(chunks_raw, embeddings):
            chunks.append({
                "id": str(uuid.uuid4()),
                "chunk_index": cd["index"],
                "content": cd["content"],
                "embedding": emb,
                "metadata": {"char_start": cd["char_start"], "char_end": cd["char_end"]},
            })
        total_chunks += len(chunks)

        # File-level embedding (from first 8000 chars of full text)
        file_embedding = _embed_text(text[:8000])

        # Insights
        insight_prompt = render_prompt(
            "artifact_insight",
            artifact_name=af.name,
            artifact_content=text[:12000],
        )
        insight_system = get_system_prompt("artifact_insight")
        insight_data = _call_llm_json(insight_prompt, system_prompt=insight_system)

        entry = {
            "id": str(uuid.uuid4()),
            "file_name": af.name,
            "file_embedding": file_embedding,
            "chunks": chunks,
            "insights": insight_data,
        }
        store["artifacts"].append(entry)
        logger.info("  %s → %d chunks", af.name, len(chunks))

    print(f"  ✓ {len(store['artifacts'])} artifact(s), {total_chunks} chunks embedded")

    # Save Step 2 output (includes embeddings)
    _save_stage("2_artifacts.json", {
        "step": "2_artifact_processing",
        "total_artifacts": len(store["artifacts"]),
        "total_chunks": total_chunks,
        "artifacts": [
            {
                "id": a["id"],
                "file_name": a["file_name"],
                "file_embedding": a["file_embedding"],
                "total_chunks": len(a["chunks"]),
                "chunks": [
                    {
                        "chunk_index": c["chunk_index"],
                        "content": c["content"],
                        "metadata": c["metadata"],
                        "embedding": c["embedding"],
                    }
                    for c in a["chunks"]
                ],
                "insights": a["insights"],
            }
            for a in store["artifacts"]
        ],
    }, "artifacts")

    # ─────────────────────────────────────────────────────
    # STEP 3: Load policies & contract clauses
    # ─────────────────────────────────────────────────────
    print("\n▶ STEP 3/6: Loading policies and contract clauses")

    # Policies
    p_files = discover_files(INPUTS_DIR / "policies", {".pdf", ".txt", ".docx"})
    for pf in p_files:
        logger.info("Loading policy: %s", pf.name)
        text = extract_text(str(pf))
        if not text.strip():
            continue
        embedding = _embed_text(text[:8000])
        store["policies"].append({
            "id": str(uuid.uuid4()),
            "title": pf.stem,
            "content": text,
            "embedding": embedding,
        })

    # Contract clauses
    c_files = discover_files(INPUTS_DIR / "contract_clauses", {".pdf", ".txt", ".docx"})
    for cf in c_files:
        logger.info("Loading contract clause: %s", cf.name)
        text = extract_text(str(cf))
        if not text.strip():
            continue
        embedding = _embed_text(text[:8000])
        store["contract_clauses"].append({
            "id": str(uuid.uuid4()),
            "category": cf.stem,
            "content": text,
            "embedding": embedding,
        })

    print(f"  ✓ {len(store['policies'])} policy/policies, {len(store['contract_clauses'])} contract clause(s)")

    # Save Step 3 output (includes embeddings)
    _save_stage("3_policies_and_clauses.json", {
        "step": "3_policies_and_contract_clauses",
        "total_policies": len(store["policies"]),
        "total_contract_clauses": len(store["contract_clauses"]),
        "policies": [
            {
                "id": p["id"],
                "title": p["title"],
                "content": p["content"],
                "embedding": p["embedding"],
            }
            for p in store["policies"]
        ],
        "contract_clauses": [
            {
                "id": cc["id"],
                "category": cc["category"],
                "content": cc["content"],
                "embedding": cc["embedding"],
            }
            for cc in store["contract_clauses"]
        ],
    }, "policies & clauses")

    # ─────────────────────────────────────────────────────
    # STEP 4: Gap Analysis (RAG + LLM)
    # ─────────────────────────────────────────────────────
    print("\n▶ STEP 4/6: Running gap analysis")

    # Gather all questions
    all_questions = []
    for q in store["questionnaires"]:
        all_questions.extend(q["questions"])

    questionnaire_insights = json.dumps([
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
        for q in all_questions
    ], indent=2)

    # RAG: search artifact chunks for security-domain questions
    # (all questions except Business Information and Document Request List)
    all_chunks = []
    for art in store["artifacts"]:
        all_chunks.extend(art["chunks"])

    INFO_ONLY_SECTIONS = {"Business Information", "Document Request List",
                          "Section 0", "Section 22"}
    logger.info("Running Python cosine similarity search (pgvector fallback)")
    artifact_evidence_items = []
    searched_questions = 0
    for q in all_questions:
        # Search for all security-domain questions, not just high/critical
        if q.get("section") in INFO_ONLY_SECTIONS:
            continue
        searched_questions += 1
        query_text = f"{q['section']}: {q['question_text']}"
        if q.get("response_text"):
            query_text += f" | Response: {q['response_text'][:200]}"
        query_emb = q.get("question_embedding") or _embed_text(query_text)
        results = similarity_search(query_emb, all_chunks, top_k=3)
        for sim, chunk in results:
            artifact_evidence_items.append({
                "id": chunk["id"],
                "content": chunk["content"],
                "metadata": chunk["metadata"],
                "distance": round(1 - sim, 6),
                "matched_question": q["control_id"],
            })
    logger.info("  Searched %d security-domain questions against %d chunks",
                searched_questions, len(all_chunks))

    # Deduplicate
    seen = set()
    unique_evidence = []
    for item in artifact_evidence_items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique_evidence.append(item)
    artifact_evidence = json.dumps(unique_evidence[:100], indent=2)
    logger.info("  %d unique evidence chunks (from %d total matches)",
                len(unique_evidence[:100]), len(artifact_evidence_items))

    # RAG: search policies
    policy_query_emb = _embed_text("security compliance controls")
    policy_results = similarity_search(policy_query_emb, store["policies"], top_k=5)
    policy_context = json.dumps([
        {"id": r["id"], "title": r["title"], "content": r["content"][:2000], "distance": round(1 - sim, 6)}
        for sim, r in policy_results
    ], indent=2)

    # RAG: search contract clauses
    clause_query_emb = _embed_text("vendor obligations security data protection")
    clause_results = similarity_search(clause_query_emb, store["contract_clauses"], top_k=5)
    contract_context = json.dumps([
        {"id": r["id"], "category": r["category"], "content": r["content"][:2000], "distance": round(1 - sim, 6)}
        for sim, r in clause_results
    ], indent=2)

    # LLM gap analysis
    gap_prompt = render_prompt("gap_analysis", **{
        "questionnaire_insights": questionnaire_insights,
        "artifact_evidence": artifact_evidence,
        "policy_context": policy_context,
        "contract_context": contract_context,
    })
    gap_system = get_system_prompt("gap_analysis")
    gap_result = _call_llm_json(gap_prompt, system_prompt=gap_system)

    question_map = {q["control_id"]: q["id"] for q in all_questions if q.get("control_id")}

    for gd in gap_result.get("gaps", []):
        gap_entry = {
            "id": str(uuid.uuid4()),
            "gap_type": gd.get("gap_type", "unknown"),
            "description": gd.get("description", ""),
            "severity": gd.get("severity", "medium"),
            "related_question_id": gd.get("related_question_id"),
            "source_refs": gd.get("source_refs"),
            "evidence_assessment": gd.get("evidence_assessment"),
        }
        store["gaps"].append(gap_entry)

    print(f"  ✓ {len(store['gaps'])} gaps identified")
    for g in store["gaps"]:
        print(f"    [{g['severity'].upper():>8s}] {g['gap_type']}: {g['description'][:80]}")

    # Save Step 4 output
    _save_stage("4_gap_analysis.json", {
        "step": "4_gap_analysis",
        "total_gaps": len(store["gaps"]),
        "security_questions_searched": searched_questions,
        "evidence_chunks_matched": len(unique_evidence),
        "severity_breakdown": {s: sum(1 for g in store["gaps"] if g["severity"] == s) for s in {g["severity"] for g in store["gaps"]}},
        "coverage_summary": gap_result.get("coverage_summary", {}),
        "gaps": store["gaps"],
        "rag_evidence_sample": unique_evidence[:20],
    }, "gap analysis")

    # ─────────────────────────────────────────────────────
    # STEP 5: Risk Assessment
    # ─────────────────────────────────────────────────────
    print("\n▶ STEP 5/6: Running risk assessment")

    gaps_data = json.dumps([
        {
            "gap_id": g["id"],
            "gap_type": g["gap_type"],
            "description": g["description"],
            "severity": g["severity"],
            "source_refs": g["source_refs"],
        }
        for g in store["gaps"]
    ], indent=2)

    vendor_context = json.dumps({"vendor_name": "Adobe", "vendor_domain": "adobe.com"})

    risk_prompt = render_prompt("risk_assessment", **{
        "gaps_data": gaps_data,
        "vendor_context": vendor_context,
    })
    risk_system = get_system_prompt("risk_assessment")
    risk_result = _call_llm_json(risk_prompt, system_prompt=risk_system)

    gap_id_set = {g["id"] for g in store["gaps"]}
    for score in risk_result.get("risk_scores", []):
        gid = score.get("gap_id", "")
        if gid not in gap_id_set:
            continue
        risk_entry = {
            "id": str(uuid.uuid4()),
            "gap_id": gid,
            "risk_level": score.get("risk_level", "medium"),
            "rationale": score.get("rationale", ""),
            "remediation_plan": score.get("remediation_plan"),
            "regulatory_impact": score.get("regulatory_impact"),
            "priority": score.get("priority"),
        }
        store["risks"].append(risk_entry)

    print(f"  ✓ {len(store['risks'])} risks scored")
    for r in store["risks"]:
        print(f"    [{r['risk_level'].upper():>8s}] {r['rationale'][:80]}")

    # Save Step 5 output
    _save_stage("5_risk_assessment.json", {
        "step": "5_risk_assessment",
        "total_risks": len(store["risks"]),
        "overall_risk_rating": risk_result.get("overall_risk_rating", "N/A"),
        "executive_summary": risk_result.get("executive_summary", ""),
        "level_breakdown": {l: sum(1 for r in store["risks"] if r["risk_level"] == l) for l in {r["risk_level"] for r in store["risks"]}},
        "risks": store["risks"],
    }, "risk assessment")

    # ─────────────────────────────────────────────────────
    # STEP 6: Generate Recommendations
    # ─────────────────────────────────────────────────────
    print("\n▶ STEP 6/6: Generating recommendations")

    risks_data = json.dumps([
        {
            "risk_id": r["id"],
            "gap_id": r["gap_id"],
            "risk_level": r["risk_level"],
            "rationale": r["rationale"],
            "gap_description": next((g["description"] for g in store["gaps"] if g["id"] == r["gap_id"]), ""),
            "gap_type": next((g["gap_type"] for g in store["gaps"] if g["id"] == r["gap_id"]), ""),
        }
        for r in store["risks"]
    ], indent=2)

    # RAG: search contract clauses for recommendation context
    rec_clause_emb = _embed_text("vendor security data protection obligations")
    rec_clause_results = similarity_search(rec_clause_emb, store["contract_clauses"], top_k=10)
    existing_clauses = json.dumps([
        {"id": r["id"], "category": r["category"], "content": r["content"][:2000], "distance": round(1 - sim, 6)}
        for sim, r in rec_clause_results
    ], indent=2)

    rec_prompt = render_prompt("recommendation", **{
        "risks_data": risks_data,
        "existing_clauses": existing_clauses,
    })
    rec_system = get_system_prompt("recommendation")
    rec_result = _call_llm_json(rec_prompt, system_prompt=rec_system)

    risk_gap_map = {r["gap_id"]: r["id"] for r in store["risks"]}

    for rec_data in rec_result.get("recommendations", []):
        gap_id_str = rec_data.get("gap_id", "")
        risk_id = risk_gap_map.get(gap_id_str)
        if not risk_id:
            continue
        rec_entry = {
            "id": str(uuid.uuid4()),
            "risk_id": risk_id,
            "gap_id": gap_id_str,
            "clause_text": rec_data.get("recommended_clause", ""),
            "justification": rec_data.get("justification", ""),
            "existing_coverage": rec_data.get("existing_coverage"),
            "priority": rec_data.get("priority"),
        }
        store["recommendations"].append(rec_entry)

    print(f"  ✓ {len(store['recommendations'])} recommendations generated")

    # Save Step 6 output
    _save_stage("6_recommendations.json", {
        "step": "6_recommendations",
        "total_recommendations": len(store["recommendations"]),
        "priority_breakdown": {p: sum(1 for r in store["recommendations"] if r.get("priority") == p) for p in {r.get("priority") for r in store["recommendations"]}},
        "recommendations": store["recommendations"],
    }, "recommendations")

    # ═══════════════════════════════════════════════════════
    #  FINAL REPORT
    # ═══════════════════════════════════════════════════════
    elapsed = time.time() - t0

    report = {
        "pipeline_mode": "mock" if not args.use_openai else "openai",
        "elapsed_seconds": round(elapsed, 2),
        "questionnaires": [
            {
                "file_name": q["file_name"],
                "vendor_name": q["parsed_content"].get("vendor_name"),
                "total_questions": len(q["questions"]),
                "analysis_result": q["analysis_result"],
            }
            for q in store["questionnaires"]
        ],
        "artifacts": [
            {
                "file_name": a["file_name"],
                "total_chunks": len(a["chunks"]),
                "insights": a["insights"],
            }
            for a in store["artifacts"]
        ],
        "policies_loaded": len(store["policies"]),
        "clauses_loaded": len(store["contract_clauses"]),
        "gaps": store["gaps"],
        "risks": store["risks"],
        "recommendations": store["recommendations"],
        "summary": {
            "total_gaps": len(store["gaps"]),
            "total_risks": len(store["risks"]),
            "total_recommendations": len(store["recommendations"]),
            "gap_severity": {},
            "risk_levels": {},
            "overall_risk_rating": risk_result.get("overall_risk_rating", "N/A"),
            "executive_summary": risk_result.get("executive_summary", ""),
        },
    }

    # Severity/level counts
    for g in store["gaps"]:
        sev = g["severity"]
        report["summary"]["gap_severity"][sev] = report["summary"]["gap_severity"].get(sev, 0) + 1
    for r in store["risks"]:
        lvl = r["risk_level"]
        report["summary"]["risk_levels"][lvl] = report["summary"]["risk_levels"].get(lvl, 0) + 1

    # ── Print report ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("  TPRM ASSESSMENT REPORT")
    print("=" * 70)
    print(f"  Mode:             {'MOCK (no OpenAI calls)' if not args.use_openai else 'LIVE (OpenAI API)'}")
    print(f"  Elapsed:          {elapsed:.1f}s")
    print(f"  Questionnaires:   {len(store['questionnaires'])}")
    print(f"  Total Questions:  {total_questions}")
    print(f"  Artifacts:        {len(store['artifacts'])} ({total_chunks} chunks)")
    print(f"  Policies:         {len(store['policies'])}")
    print(f"  Contract Clauses: {len(store['contract_clauses'])}")

    print(f"\n--- Gap Summary ({len(store['gaps'])} total) ---")
    for sev, cnt in sorted(report["summary"]["gap_severity"].items()):
        print(f"  {sev:>10s}: {cnt}")

    print(f"\n--- Risk Summary ({len(store['risks'])} total) ---")
    print(f"  Overall Rating: {report['summary']['overall_risk_rating']}")
    for lvl, cnt in sorted(report["summary"]["risk_levels"].items()):
        print(f"  {lvl:>10s}: {cnt}")

    if report["summary"]["executive_summary"]:
        print(f"\n--- Executive Summary ---")
        print(f"  {report['summary']['executive_summary']}")

    print(f"\n--- Gaps ---")
    for i, g in enumerate(store["gaps"], 1):
        print(f"  {i}. [{g['severity'].upper()}] {g['gap_type']}")
        print(f"     {g['description']}")

    print(f"\n--- Risks ---")
    for i, r in enumerate(store["risks"], 1):
        print(f"  {i}. [{r['risk_level'].upper()}] {r['rationale']}")
        if r.get("remediation_plan"):
            print(f"     Remediation: {r['remediation_plan']}")

    print(f"\n--- Recommendations ---")
    for i, rec in enumerate(store["recommendations"], 1):
        print(f"  {i}. [{rec.get('priority', 'N/A')}] {rec['clause_text']}")
        print(f"     Justification: {rec['justification']}")

    # ── Save report ──────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "final_assessment_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  Output files:")
    print(f"    1. output/1_questionnaires.json      - Parsed questions & analysis")
    print(f"    2. output/2_artifacts.json            - Chunk previews & insights")
    print(f"    3. output/3_policies_and_clauses.json - Policies & contract clauses")
    print(f"    4. output/4_gap_analysis.json         - Identified gaps")
    print(f"    5. output/5_risk_assessment.json      - Scored risks")
    print(f"    6. output/6_recommendations.json      - Recommendations")
    print(f"    7. output/final_assessment_report.json - Consolidated report")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Run the TPRM AI pipeline locally without a server",
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
