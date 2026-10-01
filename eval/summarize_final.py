import pandas as pd

df = pd.read_csv('/home/dharani/springlens/springlens/eval/ragas_faithfulness_results.csv')
print(f'Total Rows Evaluated: {len(df)}')
print('\n=== BREAKDOWN BY PROJECT & CONDITION ===')
p_summary = df.groupby(['project', 'condition'])['faithfulness'].agg(['count', 'mean'])
print(p_summary)

print('\n=== OVERALL SUMMARY (PETCLINIC + REALWORLD) ===')
o_summary = df.groupby('condition')['faithfulness'].agg(['count', 'mean'])
print(o_summary)
