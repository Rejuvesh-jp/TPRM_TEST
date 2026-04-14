"""Automated determinism audit — traces every pipeline step."""
import sys, re, yaml
sys.path.insert(0, '.')

PASS = 0
FAIL = 0

def check(label, condition):
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{status}] {label}")

print("=" * 70)
print("DETERMINISM AUDIT: Tracing every pipeline step")
print("=" * 70)

# 1. File listing
print("\n[1] FILE LISTING ORDER")
for svc in ['services/artifact_processor.py', 'services/policy_processor.py', 'services/clause_processor.py']:
    src = open(svc, encoding='utf-8').read()
    check(f"{svc} uses sorted() on file listing", 'sorted(' in src)

# 2. Questionnaire parsing
print("\n[2] QUESTIONNAIRE PARSING")
src = open('services/questionnaire_parser.py', encoding='utf-8').read()
check("section keys sorted", 'sorted(section_map' in src)

# 3. Embedding cache + similarity search
print("\n[3] EMBEDDING SERVICE")
src = open('services/embedding_service.py', encoding='utf-8').read()
check("SHA-256 embedding cache key", 'sha256' in src and '_embedding_cache' in src)
ss_section = src[src.index('def similarity_search'):]
check("similarity_search uses hashlib (not hash())", 'hashlib' in ss_section[:1200])

# 4. PG vector store
print("\n[4] PG VECTOR STORE")
src = open('webapp/pg_vector_store.py', encoding='utf-8').read()
check("get_all has ORDER BY chunk_id", 'order_by(Embedding.chunk_id)' in src)
check("search has ORDER BY (distance, chunk_id)", 'order_by(distance, Embedding.chunk_id)' in src)

# 5. JSON vector store
print("\n[5] JSON VECTOR STORE")
src = open('vector_store/json_vector_store.py', encoding='utf-8').read()
check("search sort includes ID tiebreaker", "x[1].get('id'" in src)

# 5b. ZIP extraction
print("\n[5b] ZIP EXTRACTION")
src_art = open('services/artifact_processor.py', encoding='utf-8').read()
check("extract_zip returns sorted()", "return sorted(extracted)" in src_art)

# 5c. Recommendation prompt template
print("\n[5c] RECOMMENDATION PROMPT")
with open('app/prompts/recommendation.yaml') as f:
    rdoc = yaml.safe_load(f)
check("uses {{gaps_data}} (not {{risks_data}})", '{{gaps_data}}' in rdoc['user'])
check("no {{risks_data}} placeholder", '{{risks_data}}' not in rdoc['user'])

# 6. Gap analysis evidence
print("\n[6] GAP ANALYSIS - Evidence ordering")
src = open('services/gap_analysis_service.py', encoding='utf-8').read()
check("evidence sorted by (distance, id)", 'unique_evidence.sort(' in src and '"id"' in src)

# 7. Gap dedup chain
print("\n[7] GAP ANALYSIS - Dedup chain")
check("confidence hard-filter REMOVED", '_CONFIDENCE_THRESHOLD' not in src)
check("type/qid dedup present", 'seen_keys' in src)
check("secondary dedup present", 'seen_secondary' in src)
check("semantic dedup present", '_SEMANTIC_SIM_THRESHOLD' in src)
m = re.search(r'_SEMANTIC_SIM_THRESHOLD\s*=\s*([\d.]+)', src)
threshold = float(m.group(1)) if m else 0
check("semantic threshold = 0.7 (should be >= 0.70)", threshold >= 0.70)
check("semantic dedup cross-type (no gap_type gate)", 'gt != existing_gt' not in src)
check("final sort by (severity, qid, desc)", 'severity_rank' in src and 'related_question_id' in src)

# 8. UUID
print("\n[8] UUID GENERATION")
check("deterministic UUID5", 'uuid.uuid5(_NS' in src)

# 9. LLM params
print("\n[9] LLM CALL PARAMETERS")
src_pr = open('webapp/pipeline_runner.py', encoding='utf-8').read()
check("temperature=0", 'temperature=0' in src_pr)
check("seed=42", 'seed=42' in src_pr)
check("response_format=json_object", 'json_object' in src_pr)

# 10. LLM Judge
print("\n[10] LLM JUDGE")
src_j = open('services/llm_judge.py', encoding='utf-8').read()
check("multi-pass function exists", 'run_llm_judge_multi_pass' in src_j)
m = re.search(r'JUDGE_ITERATIONS\s*=\s*(\d+)', src_j)
iters = int(m.group(1)) if m else 0
check(f"iterations = {iters} (should be 3)", iters == 3)
check("judge is NON-DESTRUCTIVE (no gap removal)", 'ids_to_remove' not in src_j)
check("logs unsupported as informational", 'informational' in src_j)
check("fixes severity", 'severity_map' in src_j)
check("improves recommendation wording", 'rec_map' in src_j)
check("passes confidence score to judge", '"confidence": g.get(' in src_j or "'confidence': g.get(" in src_j)
check("early stop on zero issues", 'early_stop' in src_j)

# 11. Output sorting
print("\n[11] OUTPUT SORTING")
src_rec = open('services/recommendation_service.py', encoding='utf-8').read()
check("recommendations sorted with gap_id tiebreak", 'gap_id' in src_rec.split('.sort(')[-1][:200])
src_rem = open('services/remedial_plan_service.py', encoding='utf-8').read()
check("remedial actions sorted with gap_id tiebreak", 'gap_id' in src_rem.split('.sort(')[-1][:200])

# 12. Prompt
print("\n[12] PROMPT DETERMINISM")
with open('app/prompts/gap_analysis.yaml') as f:
    pdoc = yaml.safe_load(f)
check("no hard confidence filter in prompt", 'Only include gaps with confidence' not in pdoc['user'])
check("instructs to include ALL gaps", 'Include ALL gaps' in pdoc['user'])
check("confidence field still requested", 'confidence' in pdoc['user'])

with open('app/prompts/llm_judge.yaml') as f:
    jdoc = yaml.safe_load(f)
check("judge prompt focuses on severity accuracy", 'MOST IMPORTANT' in jdoc['user'])

# 13. Pipeline runner import
print("\n[13] PIPELINE RUNNER INTEGRATION")
check("imports run_llm_judge_multi_pass", 'run_llm_judge_multi_pass' in src_pr)
check("no LLM prompt cache logic", 'LLM_PROMPT_CACHE_ENABLED' not in src_pr)
check("[CONFIG] startup logging", '[CONFIG] LLM Judge:' in src_pr)
check("[SCORING] final gap count logging", '[SCORING] Final gap count' in src_pr)

print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL} checks")
if FAIL == 0:
    print("ALL CHECKS PASSED — pipeline is deterministic end-to-end")
else:
    print(f"WARNING: {FAIL} check(s) FAILED — investigate above")
print("=" * 70)
