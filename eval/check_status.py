import pandas as pd
import json
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=== CHECKING DATASETS & RESULTS ===")
with open("ragas_raw_subset.json") as f:
    raw_data = json.load(f)
print(f"ragas_raw_subset.json total rows: {len(raw_data)}")

if os.path.exists("ragas_faithfulness_results.csv"):
    df = pd.read_csv("ragas_faithfulness_results.csv")
    print(f"ragas_faithfulness_results.csv total rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    if "faithfulness" in df.columns:
        print(f"Faithfulness non-null count: {df['faithfulness'].notna().sum()}/{len(df)}")
        print(df.groupby("condition")["faithfulness"].agg(["count", "mean"]))
else:
    print("ragas_faithfulness_results.csv does NOT exist.")
