"""
rescore_with_independent_judge.py
───────────────────────────────────
Re-scores the 200 pre-generated responses in `ragas_faithfulness_results.csv`
using a DISTINCT, INDEPENDENT LLM Judge model (`gemini-3.1-flash-lite`)
to eliminate Same-Model / Self-Preference Bias!
"""
import json
import os
import time
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"Working directory: {os.getcwd()}")

from langchain_google_genai import ChatGoogleGenerativeAI

API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
if not API_KEY:
    print("ERROR: GOOGLE_API_KEY environment variable is not set!")
    exit(1)

JUDGE_MODEL_NAME = "gemini-3.1-flash-lite"

print(f"Initializing Independent Judge Model: [{JUDGE_MODEL_NAME}]...")
llm_judge = ChatGoogleGenerativeAI(model=JUDGE_MODEL_NAME, google_api_key=API_KEY, temperature=0)

INPUT_CSV = "ragas_faithfulness_results.csv"
OUTPUT_CSV = "ragas_faithfulness_dual_judge_results.csv"

if not os.path.exists(INPUT_CSV):
    print(f"ERROR: {INPUT_CSV} not found!")
    exit(1)

df = pd.read_csv(INPUT_CSV)
print(f"Loaded {len(df)} pre-generated rows from {INPUT_CSV}")

def evaluate_independent_faithfulness(question, answer, contexts):
    """Evaluate faithfulness of answer against contexts using distinct judge model."""
    context_str = "\n---\n".join(contexts[:5]) if isinstance(contexts, list) else str(contexts)
    prompt = f"""You are an independent, objective expert AI evaluator for Code RAG systems.
Your task is to strictly measure the FAITHFULNESS of the Generated Answer based ONLY on the provided Retrieved Contexts.

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
            res = llm_judge.invoke(prompt)
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
                print(" [429 Rate Limit -> Sleeping 15s]...", end="", flush=True)
                time.sleep(15)
            else:
                print(f" [Judge Err: {e} -> Sleeping 2s]...", end="", flush=True)
                time.sleep(2)

scored_rows = []

if os.path.exists(OUTPUT_CSV):
    try:
        existing_res_df = pd.read_csv(OUTPUT_CSV)
        scored_rows = existing_res_df.to_dict('records')
        print(f"✓ Resuming from checkpoint: {len(scored_rows)} / {len(df)} rows already scored.")
    except Exception:
        scored_rows = []

start_idx = len(scored_rows)
print(f"Evaluating Independent Faithfulness with [{JUDGE_MODEL_NAME}] starting from row {start_idx + 1} to {len(df)}...")

for idx in range(start_idx, len(df)):
    row = df.iloc[idx].to_dict()
    q = row['user_input']
    ans = row['response']
    ctx_raw = row['retrieved_contexts']
    cond = row['condition']
    proj = row.get('project', 'petclinic' if 'PETCLINIC' in str(row.get('id', '')) else 'realworld')

    if isinstance(ctx_raw, str) and ctx_raw.startswith('['):
        try:
            contexts = eval(ctx_raw)
        except Exception:
            contexts = [ctx_raw]
    else:
        contexts = [str(ctx_raw)]

    print(f"[{idx+1}/{len(df)}] {proj.upper()} ({cond}): Re-scoring with {JUDGE_MODEL_NAME}...", end="", flush=True)
    independent_score = evaluate_independent_faithfulness(q, ans, contexts)
    print(f" Score: {independent_score:.2f}")

    row['faithfulness_flash_lite'] = row.get('faithfulness', None)
    row['faithfulness_independent_judge'] = independent_score
    row['independent_judge_model'] = JUDGE_MODEL_NAME

    scored_rows.append(row)

    if (idx + 1) % 5 == 0 or (idx + 1) == len(df):
        out_df = pd.DataFrame(scored_rows)
        out_df.to_csv(OUTPUT_CSV, index=False)
        print(f"  ✓ Saved checkpoint: {len(out_df)}/{len(df)} rows scored!")

    time.sleep(1.5)

final_df = pd.read_csv(OUTPUT_CSV)

print("\n" + "="*80)
print(f"=== DUAL-JUDGE FAITHFULNESS COMPARISON SUMMARY (200 ROWS) ===")
print(f"Generator: gemini-3.5-flash-lite  |  Independent Judge: {JUDGE_MODEL_NAME}")
print("="*80)

summary_pj = final_df.groupby(['project', 'condition'])[['faithfulness_flash_lite', 'faithfulness_independent_judge']].mean()
print(summary_pj * 100)

print("\n" + "="*80)
print("=== OVERALL COMBINED MEANS ACROSS BOTH CORPORA ===")
print("="*80)
overall = final_df.groupby('condition')[['faithfulness_flash_lite', 'faithfulness_independent_judge']].mean()
print(overall * 100)

overall.to_csv("ragas_dual_judge_summary.csv")
print(f"\n✓ Saved detailed dual-judge results to {OUTPUT_CSV}")
print(f"✓ Saved dual-judge summary to ragas_dual_judge_summary.csv")
