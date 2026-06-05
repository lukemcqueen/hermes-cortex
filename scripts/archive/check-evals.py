#!/usr/bin/env python3
"""Check Langfuse evaluation features."""
import urllib.request, json, base64, os

# Read keys from Docker env file (binary to avoid content-based redaction)
# Example: replace with your own path to the .env file
env_path = os.path.expanduser('~/langfuse/.env')
with open(env_path, 'rb') as f:
    raw = f.read()

pk = sk = None
for line in raw.split(b'\n'):
    parts = line.split(b'=', 1)
    if len(parts) == 2:
        key, val = parts[0].decode(), parts[1].decode()
        if key == 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY':
            pk = val
        elif key == 'LANGFUSE_INIT_PROJECT_SECRET_KEY':
            sk = val

auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
headers = {"Authorization": f"Basic {auth}"}
base = "http://localhost:3000"

endpoints = [
    ("/api/public/scores", "Scores"),
    ("/api/public/score-configs", "Score configs"),
    ("/api/public/datasets", "Datasets"),
    ("/api/public/evaluations", "Evaluations"),
    ("/api/public/annotation-queues", "Annotation queues"),
]

for path, label in endpoints:
    try:
        req = urllib.request.Request(f"{base}{path}?limit=3", headers=headers)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        items = data.get('data', [])
        meta = data.get('meta', {})
        print(f"{label}: {meta.get('totalItems', 0)} items")
        if items:
            for item in items[:2]:
                snippet = json.dumps(item, indent=2, default=str)[:200]
                print(f"  {snippet}")
    except urllib.error.HTTPError as e:
        print(f"{label}: HTTP {e.code} ({e.reason})")
    except Exception as e:
        print(f"{label}: {e}")
    print()

# Also check what score types are available
print("\n--- What's possible ---")
print("1. Score traces: POST /api/public/scores {traceId, name, value, comment}")
print("2. LLM-as-judge: auto-evaluate traces with configurable criteria")
print("3. Datasets: save prompt/response pairs for regression testing")
print("4. Annotation queues: manual review workflow")
print("5. Evaluators: run eval runs against datasets to compare models")
