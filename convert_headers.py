import json

headers = {}
with open('raw_headers.txt', 'r') as f:
    for line in f:
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()

with open('headers_auth.json', 'w') as f:
    json.dump(headers, f, indent=2)
