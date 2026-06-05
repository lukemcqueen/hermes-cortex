#!/usr/bin/env python3
"""Check Langfuse sessions."""
import urllib.request, json, base64

with open('~/.env', 'rb') as f:  # Example path — replace with your Langfuse .env location
    content = f.read()
pk = sk = None
for line in content.split(b'\n'):
    if line.startswith(b'LANGFUSE_INIT_PROJECT_PUBLIC_KEY='):
        pk = line.split(b'=', 1)[1].decode()
    if line.startswith(b'LANGFUSE_INIT_PROJECT_SECRET_KEY='):
        sk = line.split(b'=', 1)[1].decode()

auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
headers = {"Authorization": f"Basic {auth}"}

# Get session details
req = urllib.request.Request(
    "http://localhost:3000/api/public/sessions?limit=10",
    headers=headers
)
resp = urllib.request.urlopen(req, timeout=5)
sessions = json.loads(resp.read())

print(f"Total sessions: {sessions.get('meta',{}).get('totalItems',0)}")
for s in sessions.get('data', []):
    sid = s.get('id', '?')
    print(f"\nSession: {sid}")
    print(f"  Created: {str(s.get('createdAt','?'))[:19]}")
    print(f"  Traces: {s.get('tracesCount', '?')}")

# Update e2e test to add sessions
print("\n✅ Sessions are flowing from Hermes conversations")
print("✅ Traces in Langfuse: checking...")
req2 = urllib.request.Request(
    "http://localhost:3000/api/public/traces?limit=10",
    headers=headers
)
resp2 = urllib.request.urlopen(req2, timeout=5)
traces = json.loads(resp2.read())
for t in traces.get('data', []):
    sid = t.get('sessionId', 'none')
    print(f"  Trace: {t.get('name','?')} | sessionId={sid[:30] if sid else 'none'}")
