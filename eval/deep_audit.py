import json

with open('/home/dharani/springlens/springlens/eval/experimental_results.json') as f:
    data = json.load(f)

conds = data['conditions']

print("=" * 70)
print("REAL RESULTS - PER-CONDITION AVERAGES (from actual API responses)")
print("=" * 70)
for c_id in ['C1', 'C2', 'C3', 'C4']:
    items = conds[c_id]
    coverages = [i['metrics']['entity_coverage'] for i in items]
    ctx_recalls = [i['metrics']['context_recall_proxy'] for i in items]
    suspect = sum(1 for i in items if i.get('suspect_output', False))
    avg_cov = sum(coverages) / len(coverages)
    avg_ctx = sum(ctx_recalls) / len(ctx_recalls)
    print(f"{c_id}: N={len(items)}, avg_entity_coverage={avg_cov:.4f}, avg_context_recall={avg_ctx:.4f}, suspect={suspect}")

print()
print("=" * 70)
print("ROOT CAUSE ANALYSIS: What sources does C3/C4 actually retrieve?")
print("=" * 70)

# Check what strategy tags appear on retrieved sources for C3/C4
for c_id in ['C1', 'C3']:
    items = conds[c_id]
    # Look at the first 5 items - what are the source files?
    print(f"\n--- {c_id} first 5 items: sources_retrieved ---")
    for item in items[:5]:
        print(f"  Q={item['id']}, sources={item.get('sources_retrieved', [])}")

print()
print("=" * 70)
print("C3 vs C1: PER-QUESTION coverage comparison (first 20)")
print("=" * 70)

# Match by question id
c1_by_id = {i['id']: i for i in conds['C1']}
c3_by_id = {i['id']: i for i in conds['C3']}
c4_by_id = {i['id']: i for i in conds['C4']}
c2_by_id = {i['id']: i for i in conds['C2']}

print(f"{'QID':<25} {'C1_cov':>8} {'C3_cov':>8} {'C4_cov':>8} {'C3>C1?':>8}")
for qid in sorted(c1_by_id.keys())[:20]:
    c1 = c1_by_id.get(qid, {}).get('metrics', {}).get('entity_coverage', 'MISSING')
    c3 = c3_by_id.get(qid, {}).get('metrics', {}).get('entity_coverage', 'MISSING')
    c4 = c4_by_id.get(qid, {}).get('metrics', {}).get('entity_coverage', 'MISSING')
    better = "YES" if isinstance(c3, float) and isinstance(c1, float) and c3 > c1 else ("SAME" if c3 == c1 else "NO")
    print(f"{qid:<25} {str(c1):>8} {str(c3):>8} {str(c4):>8} {better:>8}")

print()
print("=" * 70)
print("KEY QUESTION: Are C3/C4 retrieving cross-corpus chunks?")
print("(mixing petclinic sources with realworld questions etc.)")
print("=" * 70)

petclinic_q_ids = [i['id'] for i in conds['C1'] if i['corpus'] == 'petclinic']
realworld_q_ids = [i['id'] for i in conds['C1'] if i['corpus'] == 'spring-boot-realworld']

print(f"petclinic question count: {len(petclinic_q_ids)}")
print(f"realworld question count: {len(realworld_q_ids)}")

# For a few C3 petclinic questions, check if realworld files appear in sources
cross_corpus_count = 0
total_checked = 0
for item in conds['C3']:
    if item['corpus'] == 'petclinic':
        total_checked += 1
        sources = item.get('sources_retrieved', [])
        has_realworld = any('io/spring' in str(s) for s in sources)
        if has_realworld:
            cross_corpus_count += 1
            if cross_corpus_count <= 3:
                print(f"  CROSS-CORPUS: {item['id']} -> {sources}")

print(f"\nC3 petclinic questions with realworld sources: {cross_corpus_count}/{total_checked}")

# Same for C1
cross_corpus_c1 = 0
for item in conds['C1']:
    if item['corpus'] == 'petclinic':
        sources = item.get('sources_retrieved', [])
        has_realworld = any('io/spring' in str(s) for s in sources)
        if has_realworld:
            cross_corpus_c1 += 1

print(f"C1 petclinic questions with realworld sources: {cross_corpus_c1}/{total_checked}")

print()
print("=" * 70)
print("CHECKING: What is the fullText content for C3 vs C1 for a sample Q?")
print("(Does AST header appear in retrieved text?)")
print("=" * 70)

# Look at the very first question in each condition
sample_qid = sorted(c1_by_id.keys())[0]
print(f"Sample question: {sample_qid}")
c1_item = c1_by_id[sample_qid]
c3_item = c3_by_id.get(sample_qid)
if c3_item:
    print(f"C1 entity_coverage={c1_item['metrics']['entity_coverage']}, found_in_answer={c1_item['entities_found_in_answer']}")
    print(f"C3 entity_coverage={c3_item['metrics']['entity_coverage']}, found_in_answer={c3_item['entities_found_in_answer']}")
    print(f"C1 answer snippet: {c1_item['generated_answer'][:300]}")
    print("---")
    print(f"C3 answer snippet: {c3_item['generated_answer'][:300] if c3_item.get('generated_answer') else 'NULL'}")
else:
    print(f"C3 has no entry for {sample_qid}")
