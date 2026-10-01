import os
import sys
import json
import time
import math
import warnings
from collections import Counter
import pandas as pd

warnings.filterwarnings("ignore")

from langchain_google_genai import ChatGoogleGenerativeAI

def get_api_key():
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set!")
    return key

EXP_FILE = "/home/dharani/springlens/springlens/eval/experimental_results.json"

def get_llm():
    key = get_api_key()
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=key,
        temperature=0.2
    )

def tokenize(text):
    return [w.lower() for w in text.split() if len(w) > 2]

def compute_similarity(query_tokens, doc_tokens):
    if not query_tokens or not doc_tokens:
        return 0.0
    q_counts = Counter(query_tokens)
    d_counts = Counter(doc_tokens)
    common = set(q_counts.keys()).intersection(d_counts.keys())
    score = sum(q_counts[w] * d_counts[w] for w in common)
    denom = (math.sqrt(sum(v**2 for v in q_counts.values())) * math.sqrt(sum(v**2 for v in d_counts.values())))
    return score / denom if denom > 0 else 0.0

def retrieve_contexts(question, condition, target_project=None):
    try:
        with open(EXP_FILE) as f:
            exp_data = json.load(f)
    except Exception:
        return [], "Unknown"

    cond_items = exp_data.get("conditions", {}).get(condition, [])
    q_tokens = tokenize(question)

    scored_items = []
    for item in cond_items:
        q_id = item.get("id", "")
        proj = "realworld" if "REALWORLD" in q_id else "petclinic"
        
        if target_project and proj != target_project.lower():
            continue

        sources = item.get("sources_retrieved", [])
        content_text = " ".join([s.get("content", str(s)) if isinstance(s, dict) else str(s) for s in sources])
        q_item_text = item.get("question", "") + " " + content_text
        sim = compute_similarity(q_tokens, tokenize(q_item_text))
        scored_items.append((sim, sources, proj))

    scored_items.sort(key=lambda x: x[0], reverse=True)
    
    if not scored_items:
        return [], target_project if target_project else "Unknown"

    top_sources = scored_items[0][1]
    detected_proj = scored_items[0][2]
    contexts = [s.get("content", str(s)) if isinstance(s, dict) else str(s) for s in top_sources[:4]]
    return contexts, detected_proj

def generate_answer(llm_inst, question, condition, contexts):
    context_str = "\n---\n".join(contexts[:4]) if contexts else "No context available."
    prompt = f"""You are a senior Java & Spring Boot software architect.
Answer the following developer question strictly based on the provided retrieved code context.

Condition: {condition}
Question:
{question}

Retrieved Code Contexts:
{context_str}

Provide a clear, direct, and technical response explaining implementation details, class names, and Spring annotations.
"""
    try:
        res = llm_inst.invoke(prompt)
        content = res.content
        if isinstance(content, list):
            text = "".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content]).strip()
        else:
            text = str(content).strip()
        return text
    except Exception as e:
        return f"[Generation Error: {e}]"

def evaluate_faithfulness(llm_inst, question, answer, contexts):
    context_str = "\n---\n".join(contexts[:4]) if contexts else "No context available."
    prompt = f"""You are an expert AI evaluator for Code RAG systems.
Measure the FAITHFULNESS (0.0 to 1.0) of the Answer based strictly on the Retrieved Contexts.

Question: {question}
Retrieved Contexts:
{context_str}
Answer: {answer}

Respond ONLY with a JSON object in this exact format:
{{"faithfulness": 0.95}}
"""
    try:
        res = llm_inst.invoke(prompt)
        text = str(res.content).strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        return float(data.get("faithfulness", 0.0))
    except Exception as e:
        print(f" [Evaluation Error: {e}]", file=sys.stderr)
        raise e

def main():
    args = sys.argv[1:]
    target_proj = None
    
    if "--project" in args:
        p_idx = args.index("--project")
        if p_idx + 1 < len(args):
            target_proj = args[p_idx + 1]
            args = args[:p_idx] + args[p_idx+2:]

    question = " ".join(args).strip()

    if not question:
        question = input("\nEnter your custom Spring Boot question: ").strip()

    if not question:
        print("Please provide a question!")
        return

    llm_inst = get_llm()

    print("\n" + "="*85)
    print("🚀 LIVE GENERATION & EVALUATION ON THE SPOT FOR ALL 4 CONDITIONS")
    print(f"❓ QUESTION: \"{question}\"")
    if target_proj:
        print(f"📦 TARGET PROJECT: {target_proj.upper()}")
    print("="*85)

    cond_titles = {
        "C1": "C1: Generic Token Chunking + Dense Vector Retrieval",
        "C2": "C2: Generic Token Chunking + Hybrid Retrieval (Dense + BM25)",
        "C3": "C3: AST Framework Chunking + Dense Vector Retrieval",
        "C4": "C4: AST Framework Chunking + Hybrid Retrieval (Proposed SpringLens)"
    }

    for cond in ["C1", "C2", "C3", "C4"]:
        print(f"\n[Processing {cond}] Searching code chunks & querying Gemini...", end="", flush=True)
        contexts, detected_proj = retrieve_contexts(question, cond, target_proj)
        answer = generate_answer(llm_inst, question, cond, contexts)
        faith_score = evaluate_faithfulness(llm_inst, question, answer, contexts)
        print(" Done!")

        print("\n" + "-"*85)
        print(f"📌 {cond_titles[cond]}  [Matched Codebase: {detected_proj.upper()}]")
        print(f"⭐ Faithfulness Score: {faith_score*100:.1f}%")
        print("-"*85)
        print("🤖 GENERATED RESPONSE:")
        print(answer)
        print("\n📄 RETRIEVED CONTEXT PREVIEW:")
        preview = " ".join(contexts[:1]).replace("\n", " ")[:220]
        print(f"   {preview}... [truncated]")
        time.sleep(0.5)

if __name__ == "__main__":
    main()
