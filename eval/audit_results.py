import json

with open('/home/dharani/springlens/springlens/eval/experimental_results.json') as f:
    data = json.load(f)

print("Top-level keys:", list(data.keys()))

if 'conditions' in data:
    conds = data['conditions']
    print("Condition keys:", list(conds.keys()))
    print()
    for c_id in ['C1', 'C2', 'C3', 'C4']:
        if c_id not in conds:
            print(f"{c_id}: NOT FOUND")
            continue
        items = conds[c_id]
        coverages = [i['metrics']['entity_coverage'] for i in items]
        ctx_recalls = [i['metrics']['context_recall_proxy'] for i in items]
        has_faith = any('faithfulness' in i.get('metrics', {}) for i in items)
        suspect_count = sum(1 for i in items if i.get('suspect_output', False))
        avg_cov = sum(coverages)/len(coverages) if coverages else 0
        avg_ctx = sum(ctx_recalls)/len(ctx_recalls) if ctx_recalls else 0
        print(f"{c_id}: N={len(items)}, avg_entity_coverage={avg_cov:.3f}, avg_context_recall={avg_ctx:.3f}, suspect={suspect_count}, faithfulness_metric_exists={has_faith}")

print()
print("--- Bug check: stats script reads data['C1'] but JSON is data['conditions']['C1'] ---")
print("data['C1'] would work?", 'C1' in data)
print("data['conditions']['C1'] would work?", 'C1' in data.get('conditions', {}))

print()
print("--- Failures count ---")
failures = data.get('failures', [])
print(f"Total failures: {len(failures)}")
if failures:
    print("First 5 failures:", failures[:5])
