import json
import os
import urllib.request
import urllib.parse
import time

# Always work relative to this script's directory, regardless of where it's invoked from
os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"Working directory: {os.getcwd()}")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8080/api/test/explain"

# Project name must match exactly what was used during ingestion
# This prevents multi-corpus contamination in the retrieval step
PROJECT = "petclinic"

CONDITIONS = {
    "C1": {"strategy": "generic",       "retrievalMode": "dense"},
    "C2": {"strategy": "generic",       "retrievalMode": "hybrid"},
    "C3": {"strategy": "ast_framework", "retrievalMode": "dense"},
    "C4": {"strategy": "ast_framework", "retrievalMode": "hybrid"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Load benchmark questions and select a diverse subset
# One question per category for a balanced evaluation
# ─────────────────────────────────────────────────────────────────────────────
with open("benchmark_petclinic.json") as f:
    bench = json.load(f)

seen_cats = set()
selected = []
for item in bench:
    if item["category"] not in seen_cats:
        selected.append(item)
        seen_cats.add(item["category"])
    if len(selected) >= 5:   # 5 questions × 4 conditions = 20 API calls
        break

print(f"Selected {len(selected)} questions from {len(seen_cats)} categories:")
for s in selected:
    print(f"  [{s['category']}] {s['id']}: {s['question'][:70]}...")

print(f"\nProject filter: '{PROJECT}' — ensures no cross-corpus contamination")
print(f"Total API calls: {len(selected)} questions × {len(CONDITIONS)} conditions = "
      f"{len(selected) * len(CONDITIONS)}\n")

# ─────────────────────────────────────────────────────────────────────────────
# Live call to the RAG backend
# ─────────────────────────────────────────────────────────────────────────────
def call_live(question, cond_info, condition_id):
    params = urllib.parse.urlencode({
        "query":         question,
        "retrievalMode": cond_info["retrievalMode"],
        "strategy":      cond_info["strategy"],
        "condition":     condition_id,
        "project":       PROJECT,          # ← critical: isolates petclinic data
    })
    url = f"{BASE_URL}?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


ragas_rows = []
call_num   = 0
total      = len(selected) * len(CONDITIONS)

for item in selected:
    for cond_id, cond_info in CONDITIONS.items():
        call_num += 1
        print(f"[{call_num}/{total}] {item['id']} / {cond_id} "
              f"({cond_info['strategy']} + {cond_info['retrievalMode']}) ...",
              end=" ", flush=True)

        try:
            data = call_live(item["question"], cond_info, cond_id)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "500" in err_str or "503" in err_str:
                # Parse "retry in X.Xs" from Gemini 429 message
                import re
                m = re.search(r"retry in (\d+\.?\d*)\s*s", err_str)
                wait_secs = int(float(m.group(1))) + 5 if m else 65
                print(f"Rate limit hit — waiting {wait_secs}s then retrying ...", end=" ", flush=True)
                time.sleep(wait_secs)
                try:
                    data = call_live(item["question"], cond_info, cond_id)
                except Exception as e2:
                    print(f"FAILED after retry: {e2}")
                    continue
            else:
                print(f"FAILED: {e}")
                continue

        answer = data.get("answer")
        error  = data.get("error")

        if error:
            # Backend caught a Gemini 429 — wait 70s to let the rate-limit window reset
            print(f"SKIPPED (rate-limited) — waiting 70s before next call ...")
            time.sleep(70)
            continue

        if not answer:
            print("SKIPPED — empty answer")
            time.sleep(5)
            continue

        contexts = [
            s.get("fullText", "")
            for s in data.get("sources", [])
            if s.get("fullText")
        ]
        if not contexts:
            print("SKIPPED — no context text returned")
            time.sleep(5)
            continue

        ragas_rows.append({
            "question":  item["question"],
            "answer":    answer,
            "contexts":  contexts,
            "condition": cond_id,
            "id":        item["id"],
            "category":  item["category"],
            "project":   PROJECT,
            "strategy":  cond_info["strategy"],
            "retrieval": cond_info["retrievalMode"],
        })
        print(f"OK  ({len(contexts)} context chunks, answer={len(answer)} chars)")

        # 5-second gap after every successful call → ~12 RPM, under the 20 RPM free-tier limit
        time.sleep(5)

print(f"\n─────────────────────────────────────────────")
print(f"Collected {len(ragas_rows)} usable rows for RAGAS evaluation.")
print(f"Skipped   {total - len(ragas_rows)} rows (empty retrieval or errors).")

# Show per-condition success counts
from collections import Counter
cond_counts = Counter(r["condition"] for r in ragas_rows)
print("\nRows per condition:")
for cond in ["C1", "C2", "C3", "C4"]:
    count = cond_counts.get(cond, 0)
    status = "✓" if count > 0 else "✗ WARN: no data!"
    print(f"  {cond}: {count} rows  {status}")

with open("ragas_raw_subset.json", "w") as f:
    json.dump(ragas_rows, f, indent=2, ensure_ascii=False)

print("\nSaved: ragas_raw_subset.json")
print("Next step: python run_ragas_faithfulness.py")
