#!/usr/bin/env python3
"""Check Langfuse traces."""
import json, urllib.request, os
from base64 import b64encode

# Read secret key from langfuse .env file
# Example: replace with your own path to the .env file
env_path = os.path.expanduser('~/langfuse/.env')
with open(env_path, 'r') as f:
    for line in f:
        if 'LANGFUSE_INIT_PROJECT_SECRET_KEY' in line:
            sk = line.strip().split('=', 1)[1]
            break

# Build auth
pk = "pk-lf-QQruh3wQ0dqoMzIzCkYjpNmtS5rlIXnP"
auth = b64encode(f"{pk}:{sk}".encode()).decode()

req = urllib.request.Request(
    "http://localhost:3000/api/public/traces?limit=20",
    headers={"Authorization": f"Basic {auth}"}
)
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())

meta = data.get('meta', {})
traces = data.get('data', [])
print(f"Total traces: {meta.get('totalItems', 0)}")
print(f"Page: {meta.get('page', 1)}/{meta.get('totalPages', 0)}")

for t in traces[:10]:
    ts = str(t.get('timestamp', '?'))[:19]
    print(f"  [{ts}] {t.get('name', '?')}  (id: {t.get('id','?')[:16]}...)")

if not traces:
    print("  No traces found yet.")
    print()
    # Also check sessions
    req2 = urllib.request.Request(
        "http://localhost:3000/api/public/sessions?limit=5",
        headers={"Authorization": f"Basic {auth}"}
    )
    resp2 = urllib.request.urlopen(req2, timeout=10)
    sessions = json.loads(resp2.read())
    print(f"Sessions: {sessions.get('meta',{}).get('totalItems', 0)}")
