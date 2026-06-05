---
language: python
tags: [web, net, api]
title: HTTP Requests with urllib
description: Make HTTP requests using Python stdlib. No external deps needed.
source: pattern
---

```python
import urllib.request
import urllib.parse
import json

# GET
with urllib.request.urlopen('https://api.example.com/data') as resp:
    data = json.loads(resp.read().decode())

# GET with params
params = urllib.parse.urlencode({'q': 'search term', 'page': 1})
with urllib.request.urlopen(f'https://api.example.com/search?{params}') as resp:
    data = json.loads(resp.read().decode())

# POST with JSON body
body = json.dumps({'name': 'test'}).encode()
req = urllib.request.Request(
    'https://api.example.com/items',
    data=body,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())

# With timeout
try:
    with urllib.request.urlopen('https://example.com', timeout=10) as resp:
        print(resp.read()[:100])
except urllib.error.URLError as e:
    print(f'Request failed: {e}')

```
