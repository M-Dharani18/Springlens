import json

RESULTS_PATH = "/home/dharani/springlens/springlens/eval/experimental_results.json"
data = {
    "conditions": {
        "C1": [],
        "C2": [],
        "C3": [],
        "C4": []
    },
    "failures": []
}

with open(RESULTS_PATH, "w") as f:
    json.dump(data, f, indent=2)

print("EXPERIMENTAL_RESULTS_JSON_RESET_SUCCESSFUL")
