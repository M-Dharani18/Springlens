import json
import os

eval_dir = "/home/dharani/springlens/springlens/eval"

exp_file = os.path.join(eval_dir, "experimental_results.json")
if os.path.exists(exp_file):
    with open(exp_file) as f:
        data = json.load(f)
    print("=== experimental_results.json ===")
    if isinstance(data, list):
        print("Total items:", len(data))
        projects = set(d.get("project", d.get("id", "").split("_")[0]) for d in data)
        print("Projects found:", projects)
        for proj in projects:
            n = sum(1 for d in data if d.get("project", d.get("id", "").split("_")[0]).startswith(proj[:3]))
            print(f"  {proj}: {n} items")
    elif isinstance(data, dict):
        print("Keys in dict:", list(data.keys()))
else:
    print("experimental_results.json does NOT exist")
