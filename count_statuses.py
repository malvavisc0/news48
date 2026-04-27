import json
data = json.load(sys.stdin)
statuses = [a['status'] for a in data['articles']]
counts = {'empty': 0, 'downloaded': 0, 'parsed': 0, 'download-failed': 0, 'parse-failed': 0, 'fact-unchecked': 0, 'fact-checked': 0, 'unparsed': 0}
for s in statuses:
    counts[s] += 1
print('Status counts:')
for k, v in counts.items():
    print(f'{k}: {v}')
