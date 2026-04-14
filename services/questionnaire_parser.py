"""
Questionnaire Parser Service
=============================
Parses SIG Lite questionnaire PDFs extracting all questions with
their responses and justifications, organised by section.
"""

import logging
import re
import uuid

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

logger = logging.getLogger("tprm.questionnaire_parser")

# Section-number → (letter, full_name) for SIG Lite
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

# Sections that are informational only (excluded from security analysis)
INFO_ONLY_SECTIONS = {"Business Information", "Document Request List",
                      "Section 0", "Section 22"}


def parse_sig_lite_pdf(text: str) -> dict:
    """Parse SIG Lite questionnaire text extracting ALL questions with
    their responses and justifications, organised by section."""

    # Dynamically discover section headers from the text
    discovered = {}
    for m in re.finditer(r'\n(\d+)\n\d+\n([A-Z])\.\s+([^\n]+)', text):
        num = int(m.group(1))
        letter = m.group(2)
        name = m.group(3).strip()
        discovered[num] = (letter, f"{letter}. {name}")

    section_map = dict(SIG_SECTION_MAP)
    section_map.update(discovered)

    # Split into question blocks
    question_re = re.compile(r'(?:^|\n)(\d+)\.(\d+)\n', re.MULTILINE)
    matches = list(question_re.finditer(text))

    sections_dict: dict[str, list[dict]] = {}
    vendor_name = None

    for idx, m in enumerate(matches):
        sec_num = int(m.group(1))
        sub_num = int(m.group(2))

        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        block = re.sub(r'\[Page \d+\]\s*', '', block)

        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue

        question_text = lines[0]

        # Extract response
        response_text = None
        resp_match = re.search(
            r'Response\s*\nResponse\s*\n(.*?)(?=\nJustification|\nAssessment|\Z)',
            block, re.DOTALL | re.IGNORECASE,
        )
        if resp_match:
            response_text = _deduplicate_lines(resp_match.group(1).strip())

        # Extract justification
        justification = None
        just_match = re.search(
            r'Justification\s*\nJustification\s*\n(.*?)(?=\n\d+\.\d+|\Z)',
            block, re.DOTALL | re.IGNORECASE,
        )
        if just_match:
            justification = _deduplicate_lines(just_match.group(1).strip())

        # Map to section
        sec_info = section_map.get(sec_num, ("?", f"Section {sec_num}"))
        section_name = sec_info[1]
        section_letter = sec_info[0]

        control_id = f"{section_letter}.{sub_num}" if section_letter != "?" else f"{sec_num}.{sub_num}"

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


def build_questions_with_embeddings(parsed: dict, embed_fn, embed_batch_fn=None) -> list[dict]:
    """Convert parsed questionnaire into question records with separate
    question_embedding and response_embedding."""
    # Collect all questions first
    raw_entries = []
    for section in parsed.get("sections", []):
        for q in section.get("questions", []):
            q_text = q.get("question_text", "")
            resp_parts = []
            if q.get("response_text"):
                resp_parts.append(q["response_text"])
            if q.get("justification"):
                resp_parts.append(q["justification"])
            resp_text = " | ".join(resp_parts)
            raw_entries.append((section.get("name", "Unknown"), q, q_text, resp_text))

    # Batch embed when possible
    if embed_batch_fn and raw_entries:
        q_texts = [e[2] for e in raw_entries]
        r_texts = [e[3] for e in raw_entries]
        all_texts = q_texts + r_texts
        # Replace empty strings with a placeholder so batch indices stay aligned
        all_texts_safe = [t if t.strip() else " " for t in all_texts]
        all_embeddings = embed_batch_fn(all_texts_safe)
        n = len(raw_entries)
        q_embeddings = all_embeddings[:n]
        r_embeddings = all_embeddings[n:]
    else:
        q_embeddings = None
        r_embeddings = None

    questions = []
    for idx, (sec_name, q, q_text, resp_text) in enumerate(raw_entries):
        if q_embeddings is not None:
            question_embedding = q_embeddings[idx] if q_text.strip() else None
            response_embedding = r_embeddings[idx] if resp_text.strip() else None
        else:
            question_embedding = embed_fn(q_text) if q_text.strip() else None
            response_embedding = embed_fn(resp_text) if resp_text.strip() else None

        questions.append({
            "id": str(uuid.uuid5(_NS, f"q:{sec_name}:{q.get('control_id', idx)}")),
            "section": sec_name,
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
    return questions


def get_all_control_ids(parsed: dict) -> list[str]:
    """Extract all control_ids from a parsed questionnaire."""
    ids = []
    for section in parsed.get("sections", []):
        for q in section.get("questions", []):
            if q.get("control_id"):
                ids.append(q["control_id"])
    return ids


def parse_generic_questionnaire(text: str, llm_fn, file_name: str = "questionnaire") -> dict:
    """Parse any non-SIG questionnaire (e.g. Pre-Business Assessment) using the LLM.
    Returns the same structure as parse_sig_lite_pdf so the downstream pipeline
    can treat it identically."""

    # Truncate very long texts to stay within context limits
    max_chars = 30000
    truncated = text[:max_chars]
    if len(text) > max_chars:
        truncated += "\n...[truncated]..."

    system_prompt = (
        "You are an expert TPRM security analyst specializing in parsing vendor "
        "assessment questionnaires. You extract structured data from questionnaire "
        "responses with precision. Always respond with valid JSON."
    )

    user_prompt = f"""Parse the following questionnaire text into structured sections, questions, and responses.

This is a Pre-Business Assessment / vendor risk questionnaire (NOT a SIG Lite).
Extract every question and response found in the document.

For each question, extract:
- control_id: A generated identifier like "PBA.1", "PBA.2", etc. (PBA = Pre-Business Assessment)
- question_text: The full question
- response_text: The vendor's response or answer (null if not answered)
- justification: Any justification, notes, or explanation provided

Group questions into logical sections based on the document structure.

Return a JSON object:
{{
  "vendor_name": "extracted vendor name or null",
  "questionnaire_type": "Pre-Business Assessment",
  "total_questions": <count>,
  "sections": [
    {{
      "name": "Section Name",
      "questions": [
        {{
          "control_id": "PBA.1",
          "question_text": "...",
          "response_text": "...",
          "justification": "..."
        }}
      ]
    }}
  ]
}}

QUESTIONNAIRE TEXT:
{truncated}"""

    try:
        result = llm_fn(user_prompt, system_prompt=system_prompt)
        # Validate structure
        if not isinstance(result, dict):
            raise ValueError("LLM did not return a dict")
        if "sections" not in result:
            result["sections"] = []
        if "total_questions" not in result:
            result["total_questions"] = sum(
                len(s.get("questions", [])) for s in result["sections"]
            )
        result.setdefault("vendor_name", None)
        result.setdefault("questionnaire_type", "Pre-Business Assessment")
        logger.info("LLM-parsed generic questionnaire '%s': %d sections, %d questions",
                     file_name, len(result["sections"]), result["total_questions"])
        return result
    except Exception as exc:
        logger.warning("LLM questionnaire parsing failed for '%s': %s", file_name, exc)
        # Fallback: treat entire text as a single section with no structured questions
        return {
            "vendor_name": None,
            "questionnaire_type": "Pre-Business Assessment",
            "total_questions": 0,
            "sections": [{
                "name": "Unparsed Content",
                "questions": [{
                    "control_id": "PBA.0",
                    "question_text": f"Full document content from {file_name}",
                    "response_text": text[:5000],
                    "justification": None,
                }],
            }],
        }


def _deduplicate_lines(text: str) -> str | None:
    """Remove consecutive duplicate lines."""
    lines = text.split('\n')
    cleaned = []
    prev = None
    for line in lines:
        line = line.strip()
        if line and line != prev:
            cleaned.append(line)
        prev = line
    return ' '.join(cleaned) if cleaned else None
