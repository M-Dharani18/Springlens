import urllib.request
import urllib.parse
import json
import time

start = time.time()
params = urllib.parse.urlencode({
    'query': 'How are validation errors handled when adding or updating a pet in PetClinic?',
    'retrievalMode': 'hybrid',
    'strategy': 'ast_framework',
    'condition': 'C4',
    'project': 'petclinic'
})
url = f'http://localhost:8080/api/test/explain?{params}'
print('Calling C4 PETCLINIC_Q01 with timeout=180...')
try:
    req = urllib.request.urlopen(url, timeout=180)
    data = json.loads(req.read().decode())
    print('SUCCESS in', round(time.time() - start, 2), 's')
    print('Answer length:', len(data.get('answer', '')))
    print('Answer snippet:', data.get('answer', '')[:200])
    print('Sources:', [s['filePath'] for s in data.get('sources', [])])
except Exception as e:
    print('EXCEPTION in', round(time.time() - start, 2), 's:', e)
