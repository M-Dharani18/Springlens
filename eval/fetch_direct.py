"""
fetch_direct.py
───────────────
Bypasses Spring AI's retry layer entirely.
- Retrieval: calls Spring Boot backend (dense/hybrid search, no LLM)
- Generation: calls Gemini directly from Python via google-generativeai
- Rate limiting: precise 4-second sleep between every Gemini call
"""
import json
import os
import re
import time
import urllib.request
import urllib.parse

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"Working directory: {os.getcwd()}")

# ── Config ─────────────────────────────────────────────────────────────────
BACKEND_RETRIEVE_URL = "http://localhost:8080/api/test/retrieve"  # retrieval only, no LLM!
PROJECT       = "petclinic"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
# gemini-3.5-flash-lite: high RPD free tier, fast, current
GEMINI_MODEL  = "gemini-3.5-flash-lite"

# Free tier: 20 RPM → wait 4s between calls = 15 RPM (safe margin)
CALL_DELAY_SEC     = 4
RATE_LIMIT_WAIT    = 70   # seconds to wait after a 429

if not GOOGLE_API_KEY:
    print("ERROR: GOOGLE_API_KEY env var not set.")
    print("  Run: export GOOGLE_API_KEY='AIza...'")
    exit(1)

CONDITIONS = {
    "C1": {"strategy": "generic",       "retrievalMode": "dense"},
    "C2": {"strategy": "generic",       "retrievalMode": "hybrid"},
    "C3": {"strategy": "ast_framework", "retrievalMode": "dense"},
    "C4": {"strategy": "ast_framework", "retrievalMode": "hybrid"},
}

# ── Load BOTH benchmarks ───────────────────────────────────────────────────
# petclinic=30 questions, realworld=20 questions → 50 total
CORPORA = [
    {"file": "benchmark_petclinic.json",   "project": "petclinic"},
    {"file": "benchmark_realworld.json",    "project": "realworld"},
]

selected = []
for corpus in CORPORA:
    with open(corpus["file"]) as f:
        items = json.load(f)
    for item in items:
        item["project"] = corpus["project"]   # tag each question with its project
        selected.append(item)

print(f"\nLoaded {len(selected)} questions across both corpora:")
for corpus in CORPORA:
    n = sum(1 for s in selected if s["project"] == corpus["project"])
    print(f"  {corpus['project']}: {n} questions")
print(f"\nTotal API calls: {len(selected)} × {len(CONDITIONS)} = {len(selected)*len(CONDITIONS)}")
est_min = len(selected) * len(CONDITIONS) * CALL_DELAY_SEC // 60
print(f"Estimated time: ~{est_min}–{est_min+5} minutes (at {CALL_DELAY_SEC}s/call)\n")

# ── Retrieval: calls backend (returns chunks, Spring Boot does search only) ──
def fetch_chunks(question, cond_info, cond_id, project):
    """
    Calls backend /retrieve endpoint — ONLY does vector/hybrid search, NO LLM.
    Zero Gemini API calls, zero rate limit risk from the backend.
    """
    params = urllib.parse.urlencode({
        "query":         question,
        "retrievalMode": cond_info["retrievalMode"],
        "strategy":      cond_info["strategy"],
        "condition":     cond_id,
        "project":       project,
    })
    req = urllib.request.Request(f"{BACKEND_RETRIEVE_URL}?{params}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

# ── Generation: direct Python → Gemini (no Spring AI, no retry layer) ──────
def call_gemini_direct(question, context_chunks, retries=3):
    """
    Calls Gemini directly via google.genai Python SDK (new unified SDK).
    Has its own retry-with-backoff logic that respects the rate-limit window.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai not installed.\n"
            "Run: pip install google-genai"
        )

    client = genai.Client(api_key=GOOGLE_API_KEY)

    context_text = "\n\n".join(
        f"[File: {c.get('filePath','?')}]\n{c.get('fullText', c.get('preview',''))}"
        for c in context_chunks if c.get("fullText") or c.get("preview")
    )

    prompt = f"""You are an expert Java Spring Boot architect helping a developer understand a codebase.

Based ONLY on the following retrieved source code context, answer the question below.
Do not use any knowledge outside the provided context.

=== CONTEXT ===
{context_text}
=== END CONTEXT ===

Developer Question: {question}

Provide a concise, grounded architectural explanation (max 250 words)."""

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                m = re.search(r"retry in (\d+\.?\d*)\s*s", err_str)
                wait = int(float(m.group(1))) + 5 if m else RATE_LIMIT_WAIT
                print(f"\n    [429] Rate limit — waiting {wait}s (attempt {attempt+1}/{retries}) ...", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Gemini failed after {retries} attempts")

# ── Check if google-genai is installed ──────────────────────────────────────
try:
    from google import genai as _genai_check
    print("✓ google-genai package available")
except ImportError:
    print("Installing google-genai ...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai", "-q"])
    from google import genai as _genai_check
    print("✓ google-genai installed")

# ── Main loop ────────────────────────────────────────────────────────────────
ragas_rows = []
call_num   = 0
total      = len(selected) * len(CONDITIONS)

for item in selected:
    for cond_id, cond_info in CONDITIONS.items():
        call_num += 1
        print(f"[{call_num}/{total}] {item['id']} / {cond_id} "
              f"({cond_info['strategy']} + {cond_info['retrievalMode']}) ...",
              end=" ", flush=True)

        # ── Step 1: Retrieval from Spring Boot backend ──
        project = item["project"]   # petclinic or realworld
        try:
            backend_data = fetch_chunks(item["question"], cond_info, cond_id, project)
        except Exception as e:
            print(f"RETRIEVAL_FAILED: {e}")
            time.sleep(CALL_DELAY_SEC)
            continue

        # ── Step 2: Get context chunks from /retrieve response ──
        # /retrieve returns {"chunks": [...]} — no LLM, pure retrieval
        sources = backend_data.get("chunks", [])
        chunks  = [s for s in sources if s.get("fullText")]

        if not chunks:
            print(f"SKIPPED — no fullText chunks (chunkCount={backend_data.get('chunkCount', 0)})")
            time.sleep(CALL_DELAY_SEC)
            continue

        # ── Step 3: Generate answer directly from Python → Gemini ──
        print(f"gen ({len(chunks)} chunks) ...", end=" ", flush=True)
        try:
            answer = call_gemini_direct(item["question"], chunks)
            print(f"OK ({len(answer)} chars)")
        except Exception as e:
            print(f"GEMINI_FAILED: {e}")
            time.sleep(CALL_DELAY_SEC)
            continue

        contexts = [s.get("fullText", "") for s in chunks]

        ragas_rows.append({
            "question":  item["question"],
            "answer":    answer,
            "contexts":  contexts,
            "condition": cond_id,
            "id":        item["id"],
            "category":  item["category"],
            "project":   item["project"],   # petclinic or realworld
            "strategy":  cond_info["strategy"],
            "retrieval": cond_info["retrievalMode"],
        })

        # Precise rate-limit guard: 4s between every Gemini call
        time.sleep(CALL_DELAY_SEC)

# ── Save ─────────────────────────────────────────────────────────────────────
print(f"\n{'─'*55}")
print(f"Collected {len(ragas_rows)} / {total} rows")

from collections import Counter
counts   = Counter(r["condition"] for r in ragas_rows)
projects = Counter(r["project"]   for r in ragas_rows)

print(f"\nBy condition:")
for cond in ["C1","C2","C3","C4"]:
    n = counts.get(cond, 0)
    print(f"  {cond}: {n} rows  {'✓' if n > 0 else '✗ WARNING: no data'}")

print(f"\nBy project:")
for proj, n in sorted(projects.items()):
    print(f"  {proj}: {n} rows")

with open("ragas_raw_subset.json", "w") as f:
    json.dump(ragas_rows, f, indent=2, ensure_ascii=False)

print(f"\nSaved → ragas_raw_subset.json  ({len(ragas_rows)} rows total)")
print(f"Next  → python entity_coverage_gemini.py  (instant)")
print(f"Next  → python run_ragas_faithfulness.py  (~35 min)")
