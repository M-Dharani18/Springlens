"""
run_ragas_faithfulness.py — RATE-LIMIT SAFE & ROBUST CONTENT PARSING
───────────────────────────────────────────────────────────────────────
- 85 rows validly scored on disk!
- Fixes `res.content` list object parsing bug.
- Evaluates remaining 35 rows with gemini-3.5-flash-lite and new project key.
"""
import json
import os
import time
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"Working directory: {os.getcwd()}")

from langchain_google_genai import ChatGoogleGenerativeAI

raw_keys = os.environ.get("GOOGLE_API_KEY", "").strip()
if not raw_keys:
    print("ERROR: export GOOGLE_API_KEY='...' first")
    exit(1)

API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
current_key_idx = 0

def get_llm(key_index):
    k = API_KEYS[key_index % len(API_KEYS)]
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=k,
        temperature=0,
    )

llm = get_llm(current_key_idx)

# Load full dataset (120 rows)
with open("ragas_raw_subset.json") as f:
    all_rows = json.load(f)

print(f"Loaded total dataset: {len(all_rows)} rows")

RESULTS_CSV = "ragas_faithfulness_results.csv"

# Load existing results & clean fallback rows
if os.path.exists(RESULTS_CSV):
    existing_df = pd.read_csv(RESULTS_CSV)
    if "faithfulness" in existing_df.columns:
        valid_df = existing_df.dropna(subset=["faithfulness"])
        valid_df.to_csv(RESULTS_CSV, index=False)
        scored_keys = set(zip(valid_df["id"].astype(str), valid_df["condition"].astype(str)))
        current_df = valid_df.copy()
    else:
        current_df = pd.DataFrame()
        scored_keys = set()
else:
    current_df = pd.DataFrame()
    scored_keys = set()

pending_rows = [r for r in all_rows if (str(r["id"]), str(r["condition"])) not in scored_keys]

print(f"✓ Already scored valid rows: {len(all_rows) - len(pending_rows)}")
print(f"➜ Pending rows to score: {len(pending_rows)}\n")

def evaluate_faithfulness_single_call(question, answer, contexts):
    global current_key_idx, llm
    context_str = "\n---\n".join(contexts[:5])
    prompt = f"""You are an expert AI evaluator for Code RAG system output.
Your task is to measure the FAITHFULNESS of the Generated Answer based ONLY on the provided Retrieved Contexts.

DEFINITION:
- Faithfulness (0.0 to 1.0): Are all factual claims, class names, method calls, and logic in the Generated Answer directly supported by the Retrieved Contexts?
- 1.0 = Complete faithfulness (all claims are verified by retrieved contexts).
- 0.0 = Complete hallucination (claims contradict or do not exist in retrieved contexts).

User Question:
{question}

Retrieved Code Contexts:
{context_str}

Generated Answer:
{answer}

Respond ONLY with a JSON object in this exact format:
{{"faithfulness": 0.85, "reasoning": "brief 1-sentence explanation"}}
"""
    while True:
        try:
            res = llm.invoke(prompt)
            content = res.content
            if isinstance(content, list):
                text = "".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content]).strip()
            else:
                text = str(content).strip()

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            score = float(data.get("faithfulness", 0.5))
            return min(max(score, 0.0), 1.0)
        except Exception as e:
            err_msg = str(e)
            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                print(f" [Rate Limit 429 -> Sleeping 30s]...", end="", flush=True)
                time.sleep(30)
                if len(API_KEYS) > 1:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    llm = get_llm(current_key_idx)
            else:
                print(f" [Parse Error: {e} -> Retrying in 2s]...", end="", flush=True)
                time.sleep(2)

if not pending_rows:
    print("✓ All 120 rows are already scored!")
else:
    new_results = []
    total_pending = len(pending_rows)
    
    for idx, r in enumerate(pending_rows, 1):
        q_id = r["id"]
        cond = r["condition"]
        print(f"[{idx}/{total_pending}] Evaluating {q_id} ({cond})...", end="", flush=True)
        
        score = evaluate_faithfulness_single_call(r["question"], r["answer"], r["contexts"])
        print(f" Faithfulness: {score:.2f}")
        
        new_row = {
            "user_input":         r["question"],
            "retrieved_contexts": str(r["contexts"]),
            "response":           r["answer"],
            "faithfulness":       score,
            "condition":          r["condition"],
            "id":                 r["id"],
            "strategy":           r["strategy"],
            "retrieval":          r["retrieval"],
            "project":            r.get("project", "petclinic"),
        }
        new_results.append(new_row)
        
        # Save every 5 rows
        if idx % 5 == 0 or idx == total_pending:
            batch_df = pd.DataFrame(new_results)
            if len(current_df) > 0:
                current_df = pd.concat([current_df, batch_df], ignore_index=True)
            else:
                current_df = batch_df
            current_df.to_csv(RESULTS_CSV, index=False)
            new_results = []
            print(f"  ✓ Saved progress! Scored total: {len(current_df)}/120\n")
        
        time.sleep(1.5)  # 1.5s delay

# Summary output
print("\n" + "="*60)
print("=== FINAL MEAN FAITHFULNESS BY CONDITION (120 ROWS) ===")
print("="*60)
summary = current_df.groupby("condition")[["faithfulness"]].agg(["count", "mean", "min", "max"])
summary.columns = ["n_rows", "mean_faithfulness", "min", "max"]

labels = {
    "C1": "Generic Token + Dense  (baseline)",
    "C2": "Generic Token + Hybrid",
    "C3": "AST Framework + Dense",
    "C4": "AST Framework + Hybrid",
}
summary["description"] = summary.index.map(labels)
print(summary.to_string())

summary.to_csv("ragas_condition_summary.csv")
print(f"\nSaved per-row scores to {RESULTS_CSV}")
print(f"Saved condition means to ragas_condition_summary.csv")
