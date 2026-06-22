#!/usr/bin/env python3
"""Send sample traces to Langfuse via ingestion API."""
import json, uuid, urllib.request, base64

# Read keys from .env
import json, os, sys, random
from pathlib import Path

with open(str(Path.home() / '.hermes' / '.env')) as f:
    lines = f.readlines()

pub = secret = ''
for line in lines:
    if line.startswith('HERMES_LANGFUSE_PUBLIC_KEY='):
        pub = line.strip().split('=', 1)[1]
    elif line.startswith('HERMES_LANGFUSE_SECRET_KEY='):
        secret = line.strip().split('=', 1)[1]

print(f"Public: {pub[:20]}...")
print(f"Secret: {secret[:10]}...")

base_url = 'http://localhost:3000'

def lf_api(method, path, body=None):
    url = f'{base_url}{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    auth = base64.b64encode(f'{pub}:{secret}'.encode()).decode()
    req.add_header('Authorization', f'Basic {auth}')
    req.add_header('Content-Type', 'application/json')
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        content = resp.read()
        return json.loads(content) if content else {'status': resp.status}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {'error': e.code, 'msg': body[:300]}

# Check health
health = lf_api('GET', '/api/public/health')
print(f"\nHealth: {json.dumps(health, indent=2)}")

# Create traces via ingestion API
print("\n=== Creating sample traces ===")

traces = [
    {
        "name": "orchestration-plan",
        "input": {"plan": "Microservices architecture with Redis queues"},
        "output": {"result": "Architecture approved"},
        "metadata": {"agent": "moses", "model": "deepseek/deepseek-v4-flash"},
        "tags": ["planning", "architecture"]
    },
    {
        "name": "text-generation",
        "input": {"prompt": "Draft a welcome email"},
        "output": {"email": "Welcome to the team!"},
        "metadata": {"agent": "titus", "model": "gpt-4", "tokens": 156},
        "tags": ["writing"]
    },
    {
        "name": "health-check",
        "input": {"scope": "all"},
        "output": {"services": ["nginx","postgres","redis","clickhouse","minio"]},
        "metadata": {"agent": "kustos", "duration_ms": 890},
        "tags": ["monitoring"]
    },
    {
        "name": "research-query",
        "input": {"query": "Langfuse setup"},
        "output": {"findings": "Postgres + ClickHouse + Redis + MinIO"},
        "metadata": {"agent": "gisu"},
        "tags": ["research"]
    },
    {
        "name": "cron-auto-fix",
        "input": {"job": "weekly-maintenance"},
        "output": {"fixed": ["permissions","disk"]},
        "metadata": {"agent": "joseph", "duration_ms": 4200},
        "tags": ["automation"]
    }
]

for t in traces:
    trace_id = str(uuid.uuid4())
    ingestion = {
        "batch": [{
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": "2026-06-17T02:30:00.000Z",
            "body": {
                "id": trace_id,
                "name": t["name"],
                "input": t["input"],
                "output": t["output"],
                "metadata": t["metadata"],
                "tags": t["tags"]
            }
        }]
    }
    
    result = lf_api('POST', '/api/public/ingestion', ingestion)
    if 'error' in result:
        print(f"❌ {t['name']}: HTTP {result['error']} - {result['msg'][:100]}")
    else:
        print(f"✅ {t['name']} (from {t['metadata']['agent']})")
    
    # Add generation for first 3
    if traces.index(t) < 3:
        gen_ingestion = {
            "batch": [{
                "id": str(uuid.uuid4()),
                "type": "generation-create",
                "timestamp": "2026-06-17T02:30:01.000Z",
                "body": {
                    "traceId": trace_id,
                    "name": f"{t['name']}-gen",
                    "model": t['metadata'].get('model', 'deepseek/deepseek-v4-flash'),
                    "modelParameters": {"temperature": 0.7},
                    "input": t['input'],
                    "output": t['output'],
                    "usage": {"input": 50, "output": 120, "total": 170}
                }
            }]
        }
        result = lf_api('POST', '/api/public/ingestion', gen_ingestion)
        if 'error' not in result:
            print(f"  └─ generation added")

print("\nDone!")