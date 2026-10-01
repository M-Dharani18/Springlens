import json
import os
import pandas as pd

eval_dir = "/home/dharani/springlens/springlens/eval"

with open(os.path.join(eval_dir, "ragas_raw_subset.json")) as f:
    rows = json.load(f)

print("=== ragas_raw_subset.json ===")
print("Total rows:", len(rows))
projects = set(r.get("project", "petclinic") for r in rows)
ids = set(r["id"].split("_")[0] for r in rows)
print("Projects:", projects)
print("Question ID Prefixes:", ids)

if os.path.exists(os.path.join(eval_dir, "ragas_faithfulness_results.csv")):
    df = pd.read_csv(os.path.join(eval_dir, "ragas_faithfulness_results.csv"))
    print("\n=== ragas_faithfulness_results.csv ===")
    print("Total rows:", len(df))
    print("IDs in CSV:", set(df["id"].str.split("_").str[0]))
