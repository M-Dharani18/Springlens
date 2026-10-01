import pandas as pd

df = pd.read_csv('/home/dharani/springlens/springlens/eval/ragas_faithfulness_results.csv')

# Select clean columns without huge code chunks
clean_view = df[['project', 'condition', 'faithfulness', 'user_input']]

print("=== FIRST 10 ROWS (CLEAN VIEW) ===")
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.max_colwidth', 50)
print(clean_view.head(10))
