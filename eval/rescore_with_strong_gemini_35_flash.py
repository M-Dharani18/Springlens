"""
rescore_with_strong_gemini_35_flash.py
───────────────────────────────────────
Re-scores pre-generated responses in `ragas_faithfulness_results.csv`
using the STRONGER independent LLM Judge model (`gemini-3.5-flash`)
with Multi-Key Automatic Rotation across 3 distinct API keys!
Handles 429 Rate Limits and 503 High Demand Spikes gracefully.
"""
import json
import os
import time
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from langchain_google_genai import ChatGoogleGenerativeAI

API_KEYS = [
    os.getenv("GOOGLE_API_KEY", "YOUR_API_KEY_HERE"),
    os.getenv("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
]
# Filter out placeholder keys
API_KEYS = [k for k in API_KEYS if k != "YOUR_API_KEY_HERE"]
if not API_KEYS:
    API_KEYS = ["YOUR_API_KEY_HERE"]


current_key_index = 0

def get_judge_llm(key_index):
    key = API_KEYS[key_index % len(API_KEYS)]
    return ChatGoogleGenerativeAI(model="gemini-3.5-flash", google_api_key=key, temperature=0, request_timeout=30)

INPUT_CSV = "ragas_faithfulness_results.csv"
OUTPUT_CSV = "ragas_faithfulness_strong_judge_results.csv"

if not os.path.exists(INPUT_CSV):
    print(f"ERROR: {INPUT_CSV} not found in {os.getcwd()}")
    exit(1)

df = pd.read_csv(INPUT_CSV)
print(f"Loaded {len(df)} pre-generated rows from {INPUT_CSV}")

def evaluate_strong_judge_faithfulness(question, answer, contexts):
    """Evaluate faithfulness using gemini-3.5-flash with automatic multi-key failover."""
    global current_key_index
    context_str = "\n---\n".join(contexts[:5]) if isinstance(contexts, list) else str(contexts)
    prompt = f"""You are a rigorous, expert AI evaluator for Enterprise Code RAG systems.
Your task is to strictly measure the FAITHFULNESS of the Generated Answer based ONLY on the provided Retrieved Contexts.

DEFINITION & STRICT EVALUATION RULES:
- Faithfulness (0.0 to 1.0): Are all factual claims, Java class names, method signatures, Spring annotations, and logic in the Generated Answer directly supported by the Retrieved Contexts?
- 1.0 = Complete faithfulness (all code entities and claims are explicitly verified by retrieved contexts).
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
    attempts = 0
    max_attempts = len(API_KEYS) * 3

    while attempts < max_attempts:
        try:
            llm = get_judge_llm(current_key_index)
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
            attempts += 1
            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                prev_idx = current_key_index
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                print(f" [429 Quota Key #{prev_idx+1} -> Switch to Key #{current_key_index+1}]...", end="", flush=True)
                time.sleep(3)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                prev_idx = current_key_index
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                print(f" [503 High Demand Key #{prev_idx+1} -> Switch to Key #{current_key_index+1}]...", end="", flush=True)
                time.sleep(5)
            else:
                print(f" [Err: {str(e)[:40]} -> Retry {attempts}]...", end="", flush=True)
                time.sleep(3)

    return None

scored_rows = []

if os.path.exists(OUTPUT_CSV):
    try:
        existing_res_df = pd.read_csv(OUTPUT_CSV)
        scored_rows = existing_res_df.to_dict('records')
        print(f"✓ Resuming checkpoint: {len(scored_rows)} / {len(df)} rows already scored.")
    except Exception:
        scored_rows = []

start_idx = len(scored_rows)
print(f"Evaluating Strong Judge Faithfulness with Multi-Key Rotation starting from row {start_idx + 1} to {len(df)}...")

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

    print(f"[{idx+1}/{len(df)}] {proj.upper()} ({cond}): Key #{current_key_index+1}...", end="", flush=True)
    strong_score = evaluate_strong_judge_faithfulness(q, ans, contexts)
    
    if strong_score is None:
        print(f"\n⏹ ALL KEYS / RETRIES EXHAUSTED! Pausing at row {idx+1}. Progress saved.")
        break

    print(f" Score: {strong_score:.2f}")

    row['faithfulness_flash_lite'] = row.get('faithfulness', None)
    row['faithfulness_strong_judge'] = strong_score
    row['strong_judge_model'] = "gemini-3.5-flash"

    scored_rows.append(row)

    out_df = pd.DataFrame(scored_rows)
    out_df.to_csv(OUTPUT_CSV, index=False)

    time.sleep(2.0)

final_df = pd.read_csv(OUTPUT_CSV)

print("\n" + "="*80)
print(f"=== MULTI-KEY STRONG JUDGE FAITHFULNESS SUMMARY ({len(final_df)} / 200 ROWS) ===")
print(f"Generator: gemini-3.5-flash-lite  |  Strong Judge: gemini-3.5-flash (3 API Keys)")
print("="*80)

summary_pj = final_df.groupby(['project', 'condition'])[['faithfulness_flash_lite', 'faithfulness_strong_judge']].mean()
print(summary_pj * 100)

print("\n" + "="*80)
print("=== OVERALL COMBINED MEANS ACROSS BOTH CORPORA ===")
print("="*80)
overall = final_df.groupby('condition')[['faithfulness_flash_lite', 'faithfulness_strong_judge']].mean()
print(overall * 100)

overall.to_csv("ragas_strong_judge_summary.csv")
print(f"\n✓ Saved {len(final_df)} scored rows to {OUTPUT_CSV}")
print(f"✓ Saved updated summary to ragas_strong_judge_summary.csv")
