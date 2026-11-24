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

# Sections that are informational only (excluded from security analysis).
# Kept for backwards compatibility — prefer is_info_only_section(), which also
# recognises section names discovered dynamically from the document.
INFO_ONLY_SECTIONS = {"Business Information", "Document Request List",
                      "Section 0", "Section 22"}

# Name fragments that mark a section as informational rather than a set of
# security controls. Matched against the dynamically discovered section name,
# so renamed/renumbered sections are still classified correctly.
_INFO_ONLY_KEYWORDS = (
    "business information",
    "document request",
    "documentation",
    "additional information",
    "general information",
    "company information",
    "vendor information",
    "supplier information",
    "assessment details",
    "assessment notes",
    "instructions",
    "introduction",
)

# Section names that are purely metadata
_INFO_ONLY_EXACT = {"result", "results", "section 0"}


def is_info_only_section(name: str | None) -> bool:
    """True if a section is informational and must be excluded from gap analysis.

    Works with dynamically discovered section names, so it keeps classifying
    correctly when the questionnaire template is renamed or renumbered.
    """
    if not name:
        return False
    raw = name.strip()
    if raw in INFO_ONLY_SECTIONS:          # exact legacy names
        return True
    normalized = re.sub(r"\s+", " ", raw).lower()
    if normalized in _INFO_ONLY_EXACT:
        return True
    # Lettered SIG sections ("A. Enterprise Risk Management") are always
    # security control sections — never classify them as informational.
    if re.match(r"^[a-z]\.\s", normalized):
        return False
    return any(kw in normalized for kw in _INFO_ONLY_KEYWORDS)


# Boilerplate that OneTrust-style exports emit as numbered rows but which are
# not security questions. Without this they become "no response" gaps such as
# "No response was provided for: Thank you for completing the questionnaire."
_NON_QUESTION_PATTERNS = (
    r"^thank you\b",
    r"\bthank you for (?:completing|taking|participating|your)\b",
    r"^end of (?:the )?(?:questionnaire|assessment|section|document|survey)\b",
    r"^this (?:page|section) (?:is )?intentionally left blank\b",
    r"^no further questions\b",
    r"^document request$",
    r"^result$",
    r"^results$",
    r"^comments?$",
    r"^notes?$",
    r"^not applicable$",
    r"^n/?a$",
    r"^none$",
)
_NON_QUESTION_RE = tuple(re.compile(p, re.IGNORECASE) for p in _NON_QUESTION_PATTERNS)


def is_non_question(text: str | None) -> bool:
    """True if the extracted text is boilerplate rather than an actual question."""
    if not text:
        return True
    candidate = re.sub(r"\s+", " ", text).strip()
    if len(candidate) < 3:
        return True
    return any(rx.search(candidate) for rx in _NON_QUESTION_RE)


def _section_prefix(name: str) -> str:
    """Derive a control-ID prefix from a section name.

    "A. Access Control"   -> "A"    (lettered SIG section)
    "Business Information" -> "BI"  (initials)
    "Documentation"        -> "DOC" (first letters of a single word)
    """
    lettered = re.match(r"^([A-Z])\.\s", name)
    if lettered:
        return lettered.group(1)
    words = re.findall(r"[A-Za-z]+", name)
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    if words:
        return words[0][:3].upper()
    return "?"


# A section header in these PDF exports appears as the section number repeated
# on consecutive lines, followed by the section title repeated the same way:
#     3
#     3
#     A. Enterprise Risk Management
#     A. Enterprise Risk Management
# Requiring BOTH the number and the title to repeat is what distinguishes a real
# header from document metadata (e.g. "High risks\nHigh risks\n0").
_SECTION_HEADER_RE = re.compile(r"\n(\d{1,3})\n\1\n([^\n]{3,140}?)\s*\n\2\s*\n")
# Fallback for exports that don't duplicate lines at all.
_SECTION_HEADER_SINGLE_RE = re.compile(r"\n(\d{1,3})\n([A-Z][^\n]{2,139})\n(?=\1\.\d)")


def _discover_sections(text: str) -> dict[int, tuple[str, str]]:
    """Discover section number → (prefix, name) from the document itself.

    This is the authoritative source for section mapping so that changes to the
    questionnaire template are picked up automatically instead of relying on a
    memorised layout.
    """
    discovered: dict[int, tuple[str, str]] = {}
    for rx in (_SECTION_HEADER_RE, _SECTION_HEADER_SINGLE_RE):
        for m in rx.finditer(text):
            num = int(m.group(1))
            name = re.sub(r"\s+", " ", m.group(2)).strip()
            if not name or num in discovered:
                continue
            # A real section must actually have questions numbered "<num>.<n>"
            if not re.search(rf"(?:^|\n){num}\.\d+\n", text):
                continue
            discovered[num] = (_section_prefix(name), name)
    return discovered


# Lines that are page furniture rather than question text ("13", "/", "3 / 32")
_PAGE_NOISE_RE = re.compile(r"^(?:\d{1,4}|/|\d{1,4}\s*/\s*\d{1,4})$")
# Labels that mark the end of the question text within a block
_QUESTION_STOP_RE = re.compile(
    r"^(?:response|justification|assessment\b.*|comments?|notes?|attachments?)\s*$",
    re.IGNORECASE,
)


def _trim_captured_tail(raw: str, section_titles: frozenset) -> str:
    """Remove the next section header / page footer from a captured value.

    A question block runs until the next numbered question, so a trailing
    section header or page footer can be captured along with the response or
    justification (e.g. justification "None 6 D. Asset and Info Management").
    """
    lines = [l.strip() for l in raw.split("\n")]

    # Cut at the next section header. The header is the section title preceded
    # by its number, and both may be repeated, so walk back over the numbers.
    title_idx = next((i for i, l in enumerate(lines) if l in section_titles), None)
    if title_idx is not None:
        cut = title_idx
        while cut > 0 and re.fullmatch(r"\d{1,3}", lines[cut - 1]):
            cut -= 1
        lines = lines[:cut]

    # Drop a trailing page footer shaped as:  13 / 32
    if (len(lines) >= 3 and re.fullmatch(r"\d{1,4}", lines[-1])
            and lines[-2] == "/" and re.fullmatch(r"\d{1,4}", lines[-3])):
        lines = lines[:-3]

    return "\n".join(lines)


def _extract_question_text(lines: list[str]) -> str:
    """Rebuild the full question text from a block's leading lines.

    These exports wrap long questions across several lines and repeat every
    line twice. Taking only the first line truncated wrapped questions (e.g.
    "...PII data of" instead of "...PII data of customers or employee?").
    """
    collected: list[str] = []
    for line in lines:
        if _QUESTION_STOP_RE.match(line):
            break
        if _PAGE_NOISE_RE.match(line):
            continue
        if not collected or collected[-1] != line:   # collapse repeated lines
            collected.append(line)
    return re.sub(r"\s+", " ", " ".join(collected)).strip()


def parse_sig_lite_pdf(text: str) -> dict:
    """Parse SIG Lite questionnaire text extracting ALL questions with
    their responses and justifications, organised by section."""

    # Section mapping is driven by the document itself. The hardcoded
    # SIG_SECTION_MAP is only a fallback for exports where no headers can be
    # found — otherwise a changed template would be labelled with stale names.
    discovered = _discover_sections(text)
    if discovered:
        section_map = discovered
        logger.info("Discovered %d section header(s) dynamically: %s",
                    len(discovered),
                    {n: discovered[n][1] for n in sorted(discovered)})
    else:
        section_map = dict(SIG_SECTION_MAP)
        logger.warning(
            "No section headers found in questionnaire text — falling back to "
            "the built-in SIG Lite section map. Section names may be inaccurate "
            "if the template has changed."
        )

    # Known section titles, used to strip a trailing header off captured values
    _section_titles = frozenset(name for _, name in section_map.values())

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

        question_text = _extract_question_text(lines)

        # Skip boilerplate rows ("Thank you for completing the questionnaire.")
        # so they never surface as questions or as "no response" gaps.
        if is_non_question(question_text):
            logger.debug("Skipping non-question row %d.%d: %r",
                         sec_num, sub_num, question_text[:80])
            continue

        # Extract response. The label is repeated once per line in these PDF
        # exports, but the number of repeats varies between template versions —
        # accept one or more so responses are still detected if that changes.
        response_text = None
        resp_match = re.search(
            r'(?:^|\n)(?:Response[ \t]*\n)+(.*?)(?=\n(?:Justification|Assessment)\b|\n\d+\.\d+\n|\Z)',
            block, re.DOTALL | re.IGNORECASE,
        )
        if resp_match:
            response_text = _deduplicate_lines(
                _trim_captured_tail(resp_match.group(1).strip(), _section_titles)
            )

        # Extract justification
        justification = None
        just_match = re.search(
            r'(?:^|\n)(?:Justification[ \t]*\n)+(.*?)(?=\n(?:Response|Assessment)\b|\n\d+\.\d+\n|\Z)',
            block, re.DOTALL | re.IGNORECASE,
        )
        if just_match:
            justification = _deduplicate_lines(
                _trim_captured_tail(just_match.group(1).strip(), _section_titles)
            )

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
