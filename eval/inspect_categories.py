import json
import pandas as pd

df = pd.read_csv('/home/dharani/springlens/springlens/eval/ragas_faithfulness_results.csv')
print('CSV Columns:', df.columns.tolist())

# Inspect ragas_raw_subset.json or other source files to find how questions are mapped to category
for fname in ['ragas_raw_subset.json', 'experimental_results.json', 'eval_dataset.json', 'ground_truth.json']:
    path = f'/home/dharani/springlens/springlens/eval/{fname}'
    try:
        with open(path) as f:
            data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                print(f'{fname} keys:', list(data[0].keys()))
                print(f'Sample entry from {fname}:', {k: data[0][k] for k in data[0] if k != 'retrieved_contexts'})
            elif isinstance(data, dict):
                print(f'{fname} dict keys:', list(data.keys())[:5])
    except Exception as e:
        print(f'Could not read {fname}: {e}')
