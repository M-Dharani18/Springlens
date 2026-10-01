"""
generate_and_eval_realworld_gemini.py
──────────────────────────────────────
1. Generates high-quality answers for all 80 RealWorld test cases (20 questions × 4 conditions)
   using Gemini (`gemini-3.5-flash-lite`) based on retrieved code contexts.
2. Evaluates Faithfulness using Gemini Judge for all 80 RealWorld Gemini-generated answers.
3. Merges results with PetClinic (120 rows) for a clean, high-quality 200-row dataset!
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

def get_llm():
    k = API_KEYS[current_key_idx % len(API_KEYS)]
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=k,
        temperature=0.2,
    )

llm = get_llm()

exp_file = "experimental_results.json"
with open(exp_file) as f:
    exp_data = json.load(f)

rw_items = []
conditions_data = exp_data.get("conditions", {})
RW_REPO_ROOT = "/home/dharani/springlens/corpora/spring-boot-realworld-example-app"

for cond_name, items in conditions_data.items():
    for item in items:
        q_id = item.get("id", "")
        if "REALWORLD" in q_id:
            strat = "ast_framework" if "ast" in cond_name.lower() or cond_name in ["C3", "C4"] else "generic"
            ret   = "hybrid" if "hybrid" in cond_name.lower() or cond_name in ["C2", "C4"] else "dense"
            
            sources = item.get("sources_retrieved", [])
            contexts = []
            for s in sources:
                rel_path = s if isinstance(s, str) else s.get("path", str(s))
                abs_path = os.path.join(RW_REPO_ROOT, rel_path)
                if os.path.exists(abs_path):
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f_code:
                        contexts.append(f_code.read())
                else:
                    contexts.append(str(s))
            
            rw_items.append({
                "id":        q_id,
                "question":  item.get("question", ""),
                "contexts":  contexts,
                "condition": cond_name,
                "strategy":  strat,
                "retrieval": ret,
                "project":   "realworld",
            })

print(f"Loaded RealWorld corpus: {len(rw_items)} test cases (20 questions × 4 conditions)")

# ── 2. Helper functions for generation and evaluation ──────────────────────────
def generate_gemini_answer(question, contexts):
    """Generate comprehensive answer using Gemini based on retrieved contexts."""
    context_str = "\n---\n".join(contexts[:5]) if contexts else "No context available."
    prompt = f"""You are a senior Java & Spring Boot software architect.
Answer the following developer question strictly based on the provided retrieved code context.

Question:
{question}

Retrieved Code Contexts:
{context_str}

Provide a detailed, technical answer explaining the implementation, annotations, classes, and logic.
"""
    while True:
        try:
            res = llm.invoke(prompt)
            content = res.content
            if isinstance(content, list):
                text = "".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content]).strip()
            else:
                text = str(content).strip()
            return text
        except Exception as e:
            err_msg = str(e)
            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                print(" [Gen 429 -> Sleep 25s]...", end="", flush=True)
                time.sleep(25)
            else:
                print(f" [Gen Err: {e} -> Sleep 3s]...", end="", flush=True)
                time.sleep(3)

def evaluate_faithfulness(question, answer, contexts):
    """Evaluate faithfulness of generated answer against contexts."""
    context_str = "\n---\n".join(contexts[:5]) if contexts else "No context available."
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
                print(" [Eval 429 -> Sleep 25s]...", end="", flush=True)
                time.sleep(25)
            else:
                print(f" [Eval Err: {e} -> Sleep 2s]...", end="", flush=True)
                time.sleep(2)

# ── 3. Execute Generation & Evaluation for RealWorld ───────────────────────────
RESULTS_CSV = "ragas_faithfulness_results.csv"

# Load existing PetClinic results (120 rows)
if os.path.exists(RESULTS_CSV):
    df_existing = pd.read_csv(RESULTS_CSV)
    # Keep petclinic rows only
    pet_df = df_existing[df_existing["id"].str.contains("PETCLINIC", na=False)].copy()
    print(f"Preserving existing PetClinic valid rows: {len(pet_df)}")
else:
    pet_df = pd.DataFrame()

rw_results = []
total_rw = len(rw_items)

print(f"\nGenerating Gemini Answers & Evaluating Faithfulness for {total_rw} RealWorld items...")

for idx, item in enumerate(rw_items, 1):
    q_id = item["id"]
    cond = item["condition"]
    print(f"[{idx}/{total_rw}] {q_id} ({cond}): Generating Gemini Answer...", end="", flush=True)
    
    gemini_answer = generate_gemini_answer(item["question"], item["contexts"])
    print(" Done. Evaluating...", end="", flush=True)
    
    score = evaluate_faithfulness(item["question"], gemini_answer, item["contexts"])
    print(f" Faithfulness: {score:.2f}")
    
    rw_results.append({
        "user_input":         item["question"],
        "retrieved_contexts": str(item["contexts"]),
        "response":           gemini_answer,
        "faithfulness":       score,
        "condition":          cond,
        "id":                 q_id,
        "strategy":           item["strategy"],
        "retrieval":          item["retrieval"],
        "project":            "realworld",
    })
    
    # Save checkpoint every 5 items
    if idx % 5 == 0 or idx == total_rw:
        rw_df = pd.DataFrame(rw_results)
        combined_df = pd.concat([pet_df, rw_df], ignore_index=True) if len(pet_df) > 0 else rw_df
        combined_df.to_csv(RESULTS_CSV, index=False)
        print(f"  ✓ Saved progress! Total dataset scored: {len(combined_df)}/200\n")
    
    time.sleep(1.5)

# ── 4. Generate Final Combined Summary ─────────────────────────────────────────
full_df = pd.read_csv(RESULTS_CSV)
full_df["project"] = full_df["id"].apply(lambda x: "realworld" if "REALWORLD" in str(x) else "petclinic")

print("\n" + "="*70)
print("=== FINAL GEMINI-GENERATED FAITHFULNESS (200 ROWS) ===")
print("="*70)

summary = full_df.groupby(["project", "condition"])[["faithfulness"]].agg(["count", "mean", "min", "max"])
print(summary.to_string())

print("\n" + "="*70)
print("=== OVERALL COMBINED MEANS ACROSS BOTH CORPORA ===")
print("="*70)
overall = full_df.groupby("condition")[["faithfulness"]].agg(["count", "mean", "min", "max"])
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
print(f"\n✓ Saved 200 Gemini-generated scores to {RESULTS_CSV}")
print(f"✓ Saved final condition summary to ragas_condition_summary.csv")
