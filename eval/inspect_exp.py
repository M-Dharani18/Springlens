import json
import os

eval_dir = "/home/dharani/springlens/springlens/eval"

with open(os.path.join(eval_dir, "experimental_results.json")) as f:
    data = json.load(f)

print("=== CONDITIONS KEYS / TYPES ===")
conds = data.get("conditions", {})
if isinstance(conds, dict):
    for k, v in conds.items():
        print(f"Condition key: {k}, type: {type(v)}, len: {len(v) if hasattr(v, '__len__') else 'N/A'}")
        if isinstance(v, list) and len(v) > 0:
            print("  First item keys:", v[0].keys() if isinstance(v[0], dict) else type(v[0]))
            q_ids = [item.get("id", "") for item in v if isinstance(item, dict)]
            pet_n = sum(1 for q in q_ids if "PETCLINIC" in q)
            rw_n  = sum(1 for q in q_ids if "REALWORLD" in q)
            print(f"  -> PetClinic: {pet_n}, RealWorld: {rw_n}")
