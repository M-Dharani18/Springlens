import json
import os

eval_dir = "/home/dharani/springlens/springlens/eval"

with open(os.path.join(eval_dir, "benchmark_realworld.json")) as f:
    rw = json.load(f)

print("=== benchmark_realworld.json ===")
print("Total questions:", len(rw))
if rw:
    print("Sample question:", rw[0]["id"], rw[0]["question"])
