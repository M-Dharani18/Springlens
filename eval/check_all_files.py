import os
import pandas as pd
import json

eval_dir = "/home/dharani/springlens/springlens/eval"
print("=== FILES IN EVAL DIR ===")
for f in sorted(os.listdir(eval_dir)):
    full = os.path.join(eval_dir, f)
    if os.path.isfile(full):
        size = os.path.getsize(full)
        print(f"{f:<35} {size:>10} bytes")

print("\n=== CHECKING ragas_faithfulness_results.csv ===")
csv_path = os.path.join(eval_dir, "ragas_faithfulness_results.csv")
if os.path.exists(csv_path):
    df = pd.read_csv(csv_path)
    print(f"Total rows in CSV: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    if "faithfulness" in df.columns:
        print(f"Faithfulness non-null count: {df['faithfulness'].notna().sum()}/{len(df)}")
    if "answer_relevancy" in df.columns:
        print(f"Answer relevancy non-null count: {df['answer_relevancy'].notna().sum()}/{len(df)}")
