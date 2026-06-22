#!/usr/bin/env python3
"""Verify Langfuse setup - check traces and API keys."""
import json, urllib.request, base64

import os
from pathlib import Path

with open(str(Path.home() / '.hermes' / '.env')) as f:
    lines = f.readlines()
pub = secret = ''
for line in lines:
    if line.startswith('HERMES_LANGFUSE_PUBLIC_KEY='):
        pub = line.strip().split('=', 1)[1]
    elif line.startswith('HERMES_LANGFUSE_SECRET_KEY='):
        secret = line.strip().split('=', 1)[1]

auth = base64.b64encode(f'{pub}:{secret}'.encode()).decode()
base = 'http://127.0.0.1:3000'

def api(path):
    req = urllib.request.Request(f'{base}{path}')
    req.add_header('Authorization', f'Basic {auth}')
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        return {'error': str(e), 'body': body[:300]}

print("=== Traces ===")
traces = api('/api/public/traces?limit=10')
if 'data' in traces:
    for t in traces['data']:
        print(f"  ✅ {t['name']} — {t.get('metadata', {}).get('agent', '?')} — tags: {t.get('tags', [])}")
else:
    print(json.dumps(traces, indent=2)[:300])

print("\n=== API Keys ===")
keys = api('/api/public/keys')
if 'data' in keys:
    for k in keys['data']:
        print(f"  {k['note']}: {k['publicKey'][:30]}... scope={k.get('scope', '?')}")
else:
    print(json.dumps(keys, indent=2)[:300])