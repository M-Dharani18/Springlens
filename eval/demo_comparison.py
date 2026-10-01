import sys
import json
import os
import pandas as pd

CSV_PATH = '/home/dharani/springlens/springlens/eval/ragas_faithfulness_results.csv'
STRONG_CSV_PATH = '/home/dharani/springlens/springlens/eval/ragas_faithfulness_strong_judge_results.csv'
BENCHMARK_PETCLINIC = '/home/dharani/springlens/springlens/eval/benchmark_petclinic.json'
BENCHMARK_REALWORLD = '/home/dharani/springlens/springlens/eval/benchmark_realworld.json'

# Fallback to Windows UNC path if running on Windows
if not os.path.exists(CSV_PATH):
    CSV_PATH = r'\\wsl$\Ubuntu\home\dharani\springlens\springlens\eval\ragas_faithfulness_results.csv'
    STRONG_CSV_PATH = r'\\wsl$\Ubuntu\home\dharani\springlens\springlens\eval\ragas_faithfulness_strong_judge_results.csv'
    BENCHMARK_PETCLINIC = r'\\wsl$\Ubuntu\home\dharani\springlens\springlens\eval\benchmark_petclinic.json'
    BENCHMARK_REALWORLD = r'\\wsl$\Ubuntu\home\dharani\springlens\springlens\eval\benchmark_realworld.json'

def print_banner():
    print("=" * 100)
    print(" SPRINGLENS: FRAMEWORK-AWARE RAG ARCHITECTURAL EXPLANATION DEMO")
    print(" Side-by-Side Empirical Reviewer Display (Condition C1 vs Condition C4)")
    print("=" * 100)

def load_data():
    if not os.path.exists(CSV_PATH):
        print(f"Error: Evaluation CSV file not found at {CSV_PATH}")
        sys.exit(1)

    df_primary = pd.read_csv(CSV_PATH)
    
    if os.path.exists(STRONG_CSV_PATH):
        df_strong = pd.read_csv(STRONG_CSV_PATH)
    else:
        df_strong = df_primary

    return df_primary, df_strong

def run_demo(question_index=0, project_filter="petclinic"):
    df_primary, df_strong = load_data()

    # Filter by project if needed
    df_proj = df_primary[df_primary['project'] == project_filter]
    if df_proj.empty:
        df_proj = df_primary
        project_filter = "all"

    # Get unique questions for this project
    unique_questions = df_proj['user_input'].unique()

    if question_index >= len(unique_questions):
        question_index = 0

    target_question = unique_questions[question_index]

    # Pull real empirical rows for C1 and C4 for this question
    row_c1 = df_primary[(df_primary['user_input'] == target_question) & (df_primary['condition'] == 'C1')]
    row_c4 = df_primary[(df_primary['user_input'] == target_question) & (df_primary['condition'] == 'C4')]

    if row_c1.empty or row_c4.empty:
        # Fallback to index matching
        c1_df = df_primary[df_primary['condition'] == 'C1']
        c4_df = df_primary[df_primary['condition'] == 'C4']
        row_c1 = c1_df.iloc[question_index:question_index+1]
        row_c4 = c4_df.iloc[question_index:question_index+1]
        target_question = row_c1.iloc[0]['user_input']

    c1_rec = row_c1.iloc[0]
    c4_rec = row_c4.iloc[0]

    # Pull strong judge scores if available
    s1_rows = df_strong[(df_strong['user_input'] == target_question) & (df_strong['condition'] == 'C1')]
    s4_rows = df_strong[(df_strong['user_input'] == target_question) & (df_strong['condition'] == 'C4')]

    faith_c1_primary = c1_rec.get('faithfulness', 0.0)
    faith_c4_primary = c4_rec.get('faithfulness', 0.0)

    faith_c1_strong = s1_rows.iloc[0].get('faithfulness_strong_judge', faith_c1_primary) if not s1_rows.empty else faith_c1_primary
    faith_c4_strong = s4_rows.iloc[0].get('faithfulness_strong_judge', faith_c4_primary) if not s4_rows.empty else faith_c4_primary

    # Extract retrieved contexts dynamically
    ctx_c1_raw = str(c1_rec.get('retrieved_contexts', ''))
    ctx_c4_raw = str(c4_rec.get('retrieved_contexts', ''))

    ans_c1 = str(c1_rec.get('response', ''))
    ans_c4 = str(c4_rec.get('response', ''))

    proj_name = c1_rec.get('project', project_filter).upper()

    print_banner()
    print(f"\n[QUERY INDEX]: #{question_index + 1} / {len(unique_questions)} | [CODEBASE]: {proj_name}")
    print(f"[DEVELOPER QUESTION]: \"{target_question}\"")
    print("-" * 100)

    # -------------------------------------------------------------------------
    # CONDITION C1 OUTPUT (DYNAMICALLY READ FROM EVALUATION CSV)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print(" CONDITION C1: GENERIC TOKEN + DENSE (SPRING AI DEFAULT BASELINE)")
    print(" Chunking: TokenTextSplitter (800 Tokens) | Retrieval: Dense Similarity (PGVector)")
    print("=" * 100)
    print("[RETRIEVED CONTEXT PREVIEW (Dynamic Character Count: " + str(len(ctx_c1_raw)) + " chars)]:")
    print("  " + ctx_c1_raw[:350].replace('\n', '\n  ') + " ... [Truncated]")
    print("\n[GENERATED EXPLANATION (gemini-3.5-flash-lite)]:")
    print("  \"" + ans_c1[:400].replace('\n', '\n   ') + "...\"")
    print("\n[EMPIRICAL FAITHFULNESS EVALUATION]:")
    print(f"  - Primary Judge (Gemini 3.5 Flash Lite): {faith_c1_primary * 100:.1f}%")
    print(f"  - Independent Judge (Gemini 3.5 Flash) : {faith_c1_strong * 100:.1f}%")
    print("-" * 100)

    # -------------------------------------------------------------------------
    # CONDITION C4 OUTPUT (DYNAMICALLY READ FROM EVALUATION CSV)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print(" CONDITION C4: PROPOSED FRAMEWORK-AWARE AST + HYBRID (SPRINGLENS)")
    print(" Chunking: JavaParser AST + Spring Metadata | Retrieval: BM25 + Dense Hybrid (RRF k=60)")
    print("=" * 100)
    print("[RETRIEVED CONTEXT PREVIEW (Dynamic Character Count: " + str(len(ctx_c4_raw)) + " chars)]:")
    print("  " + ctx_c4_raw[:350].replace('\n', '\n  ') + " ... [Truncated]")
    print("\n[GENERATED EXPLANATION (gemini-3.5-flash-lite)]:")
    print("  \"" + ans_c4[:400].replace('\n', '\n   ') + "...\"")
    print("\n[EMPIRICAL FAITHFULNESS EVALUATION]:")
    print(f"  - Primary Judge (Gemini 3.5 Flash Lite): {faith_c4_primary * 100:.1f}%")
    print(f"  - Independent Judge (Gemini 3.5 Flash) : {faith_c4_strong * 100:.1f}%")
    print("=" * 100 + "\n")

if __name__ == '__main__':
    idx = 0
    proj = "petclinic"
    if len(sys.argv) > 1:
        try:
            idx = int(sys.argv[1])
        except ValueError:
            idx = 0
    if len(sys.argv) > 2:
        proj = sys.argv[2]
        
    run_demo(idx, proj)
