"""
run_ragas_resume.py
────────────────────
Resumable RAGAS evaluation — skips already-scored rows, re-runs only
failed (NaN) or missing rows. Safe to run multiple times.

Input:   ragas_raw_subset.json         (120 rows of Gemini-generated answers)
         ragas_faithfulness_results.csv (existing scores, may be partial)
Output:  ragas_faithfulness_results.csv (merged, complete)
         ragas_condition_summary.csv
"""
import json
import os
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"Working directory: {os.getcwd()}")

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.run_config import RunConfig
from datasets import Dataset

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    print("ERROR: GOOGLE_API_KEY not set! Run: export GOOGLE_API_KEY='...'")
    exit(1)

# ── Load all 120 rows ─────────────────────────────────────────────────────────
with open("ragas_raw_subset.json") as f:
    all_rows = json.load(f)
print(f"Total rows in dataset: {len(all_rows)}")

# ── Load existing results (if any) ───────────────────────────────────────────
RESULTS_CSV = "ragas_faithfulness_results.csv"
existing_df = pd.DataFrame()

if os.path.exists(RESULTS_CSV):
    existing_df = pd.read_csv(RESULTS_CSV)
    # Only check columns that actually exist (old CSV may only have faithfulness)
    check_cols = [c for c in ["faithfulness", "answer_relevancy"] if c in existing_df.columns]
    valid = existing_df.dropna(subset=check_cols, how="all") if check_cols else existing_df
    print(f"Existing results: {len(existing_df)} rows total, {len(valid)} with valid scores")
    print(f"Columns in existing CSV: {list(existing_df.columns)}")
else:
    print("No existing results found — running fresh")

# ── Identify rows that need scoring ──────────────────────────────────────────
# A row needs scoring if it has NaN faithfulness OR NaN answer_relevancy OR is missing entirely
def row_key(r):
    return (r.get("id", r.get("question", ""))[:20], r.get("condition", ""))

if len(existing_df) > 0:
    scored_keys = set()
    has_ar = "answer_relevancy" in existing_df.columns
    for _, row in existing_df.iterrows():
        faith_ok = pd.notna(row.get("faithfulness"))
        ar_ok    = pd.notna(row.get("answer_relevancy")) if has_ar else False
        # A row is fully scored only if BOTH metrics are present
        if faith_ok and ar_ok:
            q_prefix = str(row.get("user_input", ""))[:20]
            cond     = str(row.get("condition", ""))
            scored_keys.add((q_prefix, cond))
        # If no answer_relevancy column yet, nothing counts as fully scored

    pending_rows = []
    for r in all_rows:
        key = (r["question"][:20], r["condition"])
        if key not in scored_keys:
            pending_rows.append(r)
else:
    pending_rows = all_rows

print(f"\nRows already scored:  {len(all_rows) - len(pending_rows)}")
print(f"Rows pending scoring: {len(pending_rows)}")

if not pending_rows:
    print("\n✓ All rows already scored! Generating summary from existing results...")
    df = existing_df.copy()
else:
    # ── Set up judge LLM ──────────────────────────────────────────────────────
    print(f"\nUsing gemini-3.5-flash-lite as judge LLM...")
    raw_llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
    )
    raw_embeddings = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=GOOGLE_API_KEY,
    )
    judge_llm        = LangchainLLMWrapper(raw_llm)
    judge_embeddings = LangchainEmbeddingsWrapper(raw_embeddings)

    # ── Build dataset of ONLY pending rows ────────────────────────────────────
    ds = Dataset.from_list([
        {
            "user_input":         r["question"],
            "response":           r["answer"],
            "retrieved_contexts": r["contexts"],
        }
        for r in pending_rows
    ])

    run_config = RunConfig(max_workers=1, timeout=300, max_retries=1)

    print(f"Running RAGAS on {len(pending_rows)} pending rows...")
    print("Metrics: faithfulness + answer_relevancy")
    print("Timeouts → NaN (won't crash the run)\n")

    try:
        result = evaluate(
            ds,
            metrics=[faithfulness, answer_relevancy],
            llm=judge_llm,
            embeddings=judge_embeddings,
            run_config=run_config,
            raise_exceptions=False,
        )
        new_df = result.to_pandas()

        # Attach metadata from pending_rows
        new_df["condition"] = [r["condition"] for r in pending_rows]
        new_df["id"]        = [r["id"]        for r in pending_rows]
        new_df["strategy"]  = [r["strategy"]  for r in pending_rows]
        new_df["retrieval"] = [r["retrieval"] for r in pending_rows]
        new_df["project"]   = [r["project"]   for r in pending_rows]

        # ── Merge with existing valid scores ──────────────────────────────────
        if len(existing_df) > 0:
            valid_cols = [c for c in ["faithfulness", "answer_relevancy"] if c in existing_df.columns]
            valid_existing = existing_df.dropna(subset=valid_cols, how="all") if valid_cols else existing_df
            df = pd.concat([valid_existing, new_df], ignore_index=True)
            print(f"\nMerged: {len(valid_existing)} existing + {len(new_df)} new = {len(df)} total rows")
        else:
            df = new_df

    except Exception as e:
        print(f"\n[ERROR]: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

# ── Save full results ─────────────────────────────────────────────────────────
df.to_csv(RESULTS_CSV, index=False)

print("\n=== RAGAS Results per Row ===")
cols = ["id", "condition", "strategy", "retrieval", "faithfulness", "answer_relevancy"]
print(df[[c for c in cols if c in df.columns]].to_string())

print("\n=== Mean Scores by Condition ===")
metric_cols = [c for c in ["faithfulness", "answer_relevancy"] if c in df.columns]
summary = df.groupby("condition")[metric_cols].mean()
labels  = {"C1": "generic+dense", "C2": "generic+hybrid",
            "C3": "ast+dense",     "C4": "ast+hybrid"}
summary["description"] = summary.index.map(labels)
print(summary.to_string())

nan_counts = df[metric_cols].isna().sum()
if nan_counts.any():
    print(f"\nNote — NaN rows (still timed out): {nan_counts.to_dict()}")
    print("Re-run this script to retry just those rows.")

summary.to_csv("ragas_condition_summary.csv")
print("\nSaved: ragas_faithfulness_results.csv  (per-row)")
print("Saved: ragas_condition_summary.csv    (per-condition means)")
