import sys
import pandas as pd

CSV_PATH = '/home/dharani/springlens/springlens/eval/ragas_faithfulness_results.csv'

def main():
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return

    questions_df = df[['project', 'user_input']].drop_duplicates().reset_index(drop=True)

    query = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""

    if not query:
        print("=======================================================================")
        print("=== SELECT A QUESTION TO COMPARE ALL 4 CONDITIONS (C1, C2, C3, C4) ===")
        print("=======================================================================")
        for idx, row in questions_df.iterrows():
            print(f"[{idx+1:2d}] ({row['project']}) {row['user_input']}")
        print("\nUsage Examples:")
        print("  python3 compare_question.py 1          (Compares all 4 conditions for Question 1)")
        print("  python3 compare_question.py JWT        (Compares all 4 conditions for question matching 'JWT')")
        return

    selected_q = None
    if query.isdigit():
        q_idx = int(query) - 1
        if 0 <= q_idx < len(questions_df):
            selected_q = questions_df.iloc[q_idx]['user_input']
    else:
        matches = questions_df[questions_df['user_input'].str.contains(query, case=False, na=False)]
        if len(matches) > 0:
            selected_q = matches.iloc[0]['user_input']

    if not selected_q:
        print(f"❌ No question found matching: '{query}'")
        return

    sub = df[df['user_input'] == selected_q]
    project_name = sub.iloc[0]['project'] if 'project' in sub.columns else 'N/A'
    
    print("\n" + "="*85)
    print(f"❓ QUESTION [{project_name.upper()}]: {selected_q}")
    print("="*85)

    cond_names = {
        'C1': 'C1: Generic Token Chunking + Dense Vector Retrieval (Baseline)',
        'C2': 'C2: Generic Token Chunking + Hybrid Retrieval (Dense + BM25)',
        'C3': 'C3: AST Framework Chunking + Dense Vector Retrieval',
        'C4': 'C4: AST Framework Chunking + Hybrid Retrieval (Proposed SpringLens)'
    }

    for cond in ['C1', 'C2', 'C3', 'C4']:
        row_sub = sub[sub['condition'] == cond]
        print("\n" + "-"*85)
        print(f"📌 {cond_names.get(cond, cond)}")
        print("-"*85)
        
        if len(row_sub) == 0:
            print("  [No data available for this condition]")
            continue
            
        row = row_sub.iloc[0]
        score = row.get('faithfulness', 'N/A')
        resp = row.get('response', 'N/A')
        ctx = row.get('retrieved_contexts', 'N/A')
        
        if isinstance(score, (int, float)):
            print(f"⭐ Faithfulness Score: {score*100:.1f}%")
        else:
            print(f"⭐ Faithfulness Score: {score}")

        print("\n🤖 GEMINI GENERATED RESPONSE:")
        print(resp.strip() if isinstance(resp, str) else resp)

        print("\n📄 RETRIEVED CONTEXT (PREVIEW):")
        ctx_str = str(ctx).replace('\n', ' ')
        if len(ctx_str) > 250:
            print(f"   {ctx_str[:250]}... [truncated]")
        else:
            print(f"   {ctx_str}")

if __name__ == '__main__':
    main()
