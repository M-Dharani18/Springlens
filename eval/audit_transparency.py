import pandas as pd
import os

eval_dir = "/home/dharani/springlens/springlens/eval"
csv_path = os.path.join(eval_dir, "ragas_faithfulness_results.csv")

df = pd.read_csv(csv_path)

print("=== TRANSPARENCY AUDIT OF RAGAS_FAITHFULNESS_RESULTS.CSV ===")
print(f"Total Rows: {len(df)}")
print(f"Projects present: {set(df['project'])}")
print("\nScore Value Counts (Unique Scores Returned by LLM Judge):")
print(df['faithfulness'].value_counts().sort_index())

print("\n--- PetClinic Breakdown ---")
pet = df[df['project'] == 'petclinic']
print(pet.groupby('condition')['faithfulness'].agg(['count', 'mean', 'min', 'max']))

print("\n--- RealWorld Breakdown ---")
rw = df[df['project'] == 'realworld']
print(rw.groupby('condition')['faithfulness'].agg(['count', 'mean', 'min', 'max']))

print("\n--- Sample Raw Rows (PetClinic C1 vs C4) ---")
print(df[df['project']=='petclinic'][['id', 'condition', 'faithfulness']].head(8).to_string())

print("\n--- Sample Raw Rows (RealWorld C1 vs C4) ---")
print(df[df['project']=='realworld'][['id', 'condition', 'faithfulness']].head(8).to_string())
