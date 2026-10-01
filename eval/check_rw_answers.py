import json
import os

eval_dir = "/home/dharani/springlens/springlens/eval"

with open(os.path.join(eval_dir, "experimental_results.json")) as f:
    data = json.load(f)

c1 = data["conditions"]["C1"]
rw_c1 = [item for item in c1 if "REALWORLD" in item.get("id", "")]

print("=== REALWORLD IN EXPERIMENTAL_RESULTS.JSON ===")
print("Total RealWorld items in C1:", len(rw_c1))
if rw_c1:
    item = rw_c1[0]
    print("ID:", item.get("id"))
    print("Question:", item.get("question"))
    print("Generated Answer preview:", item.get("generated_answer", "")[:150])
    print("Sources Retrieved count:", len(item.get("sources_retrieved", [])))
