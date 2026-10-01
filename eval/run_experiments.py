import json
import os
import re
import time
import argparse
import threading
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://localhost:8080/api/test/explain"

# Maps benchmark corpus name -> project name stored in vector store during ingestion
# Must match exactly the projectName used when calling /api/test/ingest-project
CORPUS_TO_PROJECT = {
    "petclinic": "petclinic",
    "spring-boot-realworld": "realworld",
}

BENCHMARKS = {
    "petclinic": "/home/dharani/springlens/springlens/eval/benchmark_petclinic.json",
    "spring-boot-realworld": "/home/dharani/springlens/springlens/eval/benchmark_realworld.json",
}
RESULTS_PATH = "/home/dharani/springlens/springlens/eval/experimental_results.json"

CONDITIONS = {
    "C1": {"strategy": "generic", "retrievalMode": "dense", "description": "Generic Token + Dense"},
    "C2": {"strategy": "generic", "retrievalMode": "hybrid", "description": "Generic Token + Hybrid"},
    "C3": {"strategy": "ast_framework", "retrievalMode": "dense", "description": "AST Framework-Aware + Dense"},
    "C4": {"strategy": "ast_framework", "retrievalMode": "hybrid", "description": "AST Framework-Aware + Hybrid"},
}

GARBAGE_PATTERN = re.compile(r"(\^\[\[[AB]){3,}|(.)\2{20,}")


def is_suspect_answer(answer_text):
    if not answer_text or len(answer_text.strip()) < 15:
        return True
    if GARBAGE_PATTERN.search(answer_text):
        return True
    return False


def call_live_api(question, condition_id, cond_info, project, timeout=300):
    params = urllib.parse.urlencode({
        "query": question,
        "retrievalMode": cond_info["retrievalMode"],
        "strategy": cond_info["strategy"],
        "condition": condition_id,
        "project": project,
    })
    url = f"{BASE_URL}?{params}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode())
            return data.get("answer", ""), data.get("sources", []), None
    except Exception as e:
        return None, None, str(e)


def compute_entity_coverage(answer_text, expected_entities):
    if not answer_text or not expected_entities:
        return 0.0, []
    answer_lower = answer_text.lower()
    found = [e for e in expected_entities if e.lower() in answer_lower]
    return len(found) / len(expected_entities), found


def compute_context_recall_proxy(sources, expected_entities):
    if not sources or not expected_entities:
        return 0.0, []
    combined_text = " ".join(s.get("fullText", "") + " " + s.get("preview", "") for s in sources).lower()
    found = [e for e in expected_entities if e.lower() in combined_text]
    return len(found) / len(expected_entities), found


def load_existing_results():
    if not os.path.exists(RESULTS_PATH):
        return {c: [] for c in CONDITIONS}, [], set()
    try:
        with open(RESULTS_PATH, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        backup_path = RESULTS_PATH + ".corrupted_backup"
        os.replace(RESULTS_PATH, backup_path)
        print(f"[WARN] {RESULTS_PATH} was corrupted. Backed up to {backup_path}. Starting fresh.")
        return {c: [] for c in CONDITIONS}, [], set()
    results = data.get("conditions", {c: [] for c in CONDITIONS})
    for c in CONDITIONS:
        results.setdefault(c, [])
    completed = {(item["id"], item["condition"]) for c in results.values() for item in c}
    return results, data.get("failures", []), completed


def run(limit=None, only_corpus=None, batch_size=None, workers=3):
    all_items = []
    for corpus_name, path in BENCHMARKS.items():
        if only_corpus and corpus_name != only_corpus:
            continue
        if not os.path.exists(path):
            print(f"[WARN] Benchmark not found, skipping: {path}")
            continue
        with open(path, "r") as f:
            items = json.load(f)
        if limit:
            items = items[:limit]
        for item in items:
            item["corpus"] = corpus_name
        all_items.extend(items)

    results_by_condition, failures, completed = load_existing_results()
    print(f"[RESUME] {len(completed)} (item, condition) pairs already completed - will skip those.")

    pending = [(item, c_id, c_info) for item in all_items for c_id, c_info in CONDITIONS.items()
               if (item["id"], c_id) not in completed]
    if batch_size:
        pending = pending[:batch_size]

    total = len(pending)
    print(f"Running {total} remaining calls with {workers} parallel worker threads.")

    lock = threading.Lock()
    call_num = 0
    start_time = time.time()
    suspect_count = 0

    def process_task(task_args):
        nonlocal call_num, suspect_count
        item, c_id, c_info = task_args

        project = CORPUS_TO_PROJECT.get(item["corpus"], "")
        answer, sources, error = call_live_api(item["question"], c_id, c_info, project)

        with lock:
            call_num += 1
            elapsed = time.time() - start_time
            if error:
                print(f"[{call_num}/{total}] ({elapsed:.0f}s) {item['id']} | {c_id} ... FAILED: {error}")
                failures.append({"id": item["id"], "condition": c_id, "error": error})
            else:
                suspect = is_suspect_answer(answer)
                if suspect:
                    suspect_count += 1
                entity_cov, found_in_answer = compute_entity_coverage(answer, item["expected_entities"])
                context_rec, found_in_context = compute_context_recall_proxy(sources, item["expected_entities"])
                flag = " [SUSPECT]" if suspect else ""
                print(f"[{call_num}/{total}] ({elapsed:.0f}s) {item['id']} | {c_id} ... OK (entity_cov={entity_cov:.2f}, ctx_rec={context_rec:.2f}){flag}")

                results_by_condition[c_id].append({
                    "id": item["id"],
                    "corpus": item["corpus"],
                    "category": item["category"],
                    "question": item["question"],
                    "condition": c_id,
                    "generated_answer": answer,
                    "suspect_output": suspect,
                    "expected_entities": item["expected_entities"],
                    "entities_found_in_answer": found_in_answer,
                    "entities_found_in_context": found_in_context,
                    "metrics": {
                        "entity_coverage": round(entity_cov, 3),
                        "context_recall_proxy": round(context_rec, 3),
                    },
                    "sources_retrieved": [s.get("filePath") for s in (sources or [])],
                })

            tmp_path = RESULTS_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump({
                    "conditions": results_by_condition,
                    "failures": failures,
                    "metric_notes": {
                        "entity_coverage": "Real substring match against ground-truth entities.",
                        "context_recall_proxy": "Proxy metric from retrieved context sources.",
                        "suspect_output": "Flagged True if answer looks like degenerate/garbage output.",
                    },
                }, f, indent=2)
            os.replace(tmp_path, RESULTS_PATH)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_task, task) for task in pending]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as ex:
                    print(f"[WORKER_ERR] {ex}")
    else:
        for task in pending:
            process_task(task)

    print(f"\nDone this session. {suspect_count} suspect outputs flagged for manual review.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--corpus", type=str, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    run(limit=args.limit, only_corpus=args.corpus, batch_size=args.batch_size, workers=args.workers)
