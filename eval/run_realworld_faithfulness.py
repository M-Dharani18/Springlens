"""
run_realworld_faithfulness.py — EVALUATE CORPUS 2 (REALWORLD - 80 ROWS)
────────────────────────────────────────────────────────────────────────
- Loads 80 RealWorld items (20 questions × 4 conditions C1-C4) from `experimental_results.json`.
- Evaluates faithfulness using Gemini Cloud (`gemini-3.5-flash-lite`).
- Appends to `ragas_faithfulness_results.csv` for full 200-row combined evaluation across BOTH corpora!
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

# Load RealWorld items from experimental_results.json
exp_file = "experimental_results.json"
if not os.path.exists(exp_file):
    print("ERROR: experimental_results.json not found!")
    exit(1)

with open(exp_file) as f:
    exp_data = json.load(f)

rw_rows = []
conditions_data = exp_data.get("conditions", {})

for cond_name, items in conditions_data.items():
    for item in items:
        q_id = item.get("id", "")
        if "REALWORLD" in q_id:
            # Map strategy and retrieval
            strat = "ast_framework" if "ast" in cond_name.lower() or cond_name in ["C3", "C4"] else "generic"
            ret   = "hybrid" if "hybrid" in cond_name.lower() or cond_name in ["C2", "C4"] else "dense"
            
            # Format context strings
            sources = item.get("sources_retrieved", [])
            contexts = [s.get("content", str(s)) if isinstance(s, dict) else str(s) for s in sources]
            
            rw_rows.append({
                "id":        q_id,
                "question":  item.get("question", ""),
                "answer":    item.get("generated_answer", ""),
                "contexts":  contexts,
                "condition": cond_name,
                "strategy":  strat,
                "retrieval": ret,
                "project":   "realworld",
            })

print(f"Loaded RealWorld corpus items: {len(rw_rows)} rows (20 questions × 4 conditions)")

RESULTS_CSV = "ragas_faithfulness_results.csv"

# Load existing results (PetClinic = 120 rows)
if os.path.exists(RESULTS_CSV):
    existing_df = pd.read_csv(RESULTS_CSV)
    scored_keys = set(zip(existing_df["id"].astype(str), existing_df["condition"].astype(str)))
    current_df = existing_df.copy()
else:
    current_df = pd.DataFrame()
    scored_keys = set()

pending_rows = [r for r in rw_rows if (str(r["id"]), str(r["condition"])) not in scored_keys]

print(f"✓ Already scored rows in CSV: {len(existing_df)}")
print(f"➜ Pending RealWorld rows to score: {len(pending_rows)}\n")

def evaluate_faithfulness_single_call(question, answer, contexts):
    global current_key_idx, llm
    context_str = "\n---\n".join(contexts[:5]) if contexts else "No context provided."
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
                print(f" [Rate Limit 429 -> Sleeping 25s]...", end="", flush=True)
                time.sleep(25)
                if len(API_KEYS) > 1:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    llm = get_llm(current_key_idx)
            else:
                print(f" [Parse Error: {e} -> Retrying in 2s]...", end="", flush=True)
                time.sleep(2)

if not pending_rows:
    print("✓ All RealWorld rows are already scored!")
else:
    new_results = []
    total_pending = len(pending_rows)
    
    for idx, r in enumerate(pending_rows, 1):
        q_id = r["id"]
        cond = r["condition"]
        print(f"[{idx}/{total_pending}] Evaluating RealWorld {q_id} ({cond})...", end="", flush=True)
        
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
            "project":            "realworld",
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
            print(f"  ✓ Saved progress! Scored total: {len(current_df)}/200\n")
        
        time.sleep(1.5)  # 1.5s delay

# Overall Combined Summary Across BOTH Corpora
print("\n" + "="*70)
print("=== COMBINED FAITHFULNESS SUMMARY ACROSS BOTH CORPORA (200 ROWS) ===")
print("="*70)

current_df["project"] = current_df["id"].apply(lambda x: "realworld" if "REALWORLD" in str(x) else "petclinic")

summary = current_df.groupby(["project", "condition"])[["faithfulness"]].agg(["count", "mean"])
print(summary.to_string())

print("\n" + "="*70)
print("=== OVERALL MEAN FAITHFULNESS BY CONDITION (COMBINED) ===")
print("="*70)
overall = current_df.groupby("condition")[["faithfulness"]].agg(["count", "mean", "min", "max"])
overall.columns = ["n_rows", "mean_faithfulness", "min", "max"]

labels = {
    "C1": "Generic Token + Dense  (baseline)",
    "C2": "Generic Token + Hybrid",
    "C3": "AST Framework + Dense",
    "C4": "AST Framework + Hybrid",
}
overall["description"] = overall.index.map(labels)
print(overall.to_string())

overall.to_csv("ragas_condition_summary.csv")
print(f"\nSaved combined 200-row scores to {RESULTS_CSV}")
print(f"Saved final combined condition summary to ragas_condition_summary.csv")
