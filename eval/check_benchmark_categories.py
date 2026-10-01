import json

for bname in ['benchmark_petclinic.json', 'benchmark_realworld.json']:
    path = f'/home/dharani/springlens/springlens/eval/{bname}'
    with open(path) as f:
        data = json.load(f)
    print(f'=== {bname} ===')
    if isinstance(data, list):
        print('Total items:', len(data))
        print('Keys in item:', list(data[0].keys()))
        categories = set(item.get('category', item.get('type', item.get('question_type', 'N/A'))) for item in data)
        print('Categories found:', categories)
        for cat in categories:
            sample = [item for item in data if item.get('category', item.get('type', item.get('question_type'))) == cat]
            print(f'  Category: {cat} (count={len(sample)}) -> Sample Q: {sample[0].get(
