#!/usr/bin/env python3
"""
Populate Langfuse dashboard with comprehensive data: traces, generations,
scores, model costs, latencies, sessions across 7 days.
Uses Hermes Langfuse credentials from ~/.hermes/.env.
"""
import json, uuid, urllib.request, base64, random
from pathlib import Path
from datetime import datetime, timezone, timedelta

with open(str(Path.home() / '.hermes' / '.env')) as f:
    lines = f.readlines()
pub = secret = ''
for line in lines:
    if line.startswith('HERMES_LANGFUSE_PUBLIC_KEY='):
        pub = line.strip().split('=', 1)[1]
    elif line.startswith('HERMES_LANGFUSE_SECRET_KEY='):
        secret = line.strip().split('=', 1)[1]

base_url = 'http://localhost:3000'

def api(method, path, body=None):
    url = f'{base_url}{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    auth = base64.b64encode(f'{pub}:{secret}'.encode()).decode()
    req.add_header('Authorization', f'Basic {auth}')
    req.add_header('Content-Type', 'application/json')
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read()
        return json.loads(body) if body else {'status': resp.status}
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'msg': e.read().decode()[:200]}

models = [
    {"name": "gpt-4o", "input_price": 0.0000025, "output_price": 0.00001},
    {"name": "claude-sonnet-4", "input_price": 0.000003, "output_price": 0.000015},
    {"name": "deepseek/deepseek-v4-flash", "input_price": 0.0000005, "output_price": 0.000002},
    {"name": "qwen3-235b-a22b", "input_price": 0.000001, "output_price": 0.000003},
]
agents = ['moses', 'titus', 'kustos', 'gisu', 'joseph', 'esther', 'benaiah', 'elam']
trace_names = [
    "code-review", "deploy-rollout", "weekly-op-scan", "research-cisac",
    "db-migration", "agent-dispatch", "ui-component-test", "daily-briefing",
    "cron-remediation", "trace-analysis", "load-testing", "security-audit",
    "performance-bench", "api-integration", "docs-generation",
]
sessions = [str(uuid.uuid4()) for _ in range(5)]
score_names = ["helpfulness", "quality", "clarity", "depth"]
day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)

print(f"Creating {len(trace_names)} traces over 7 days...")
for i, name in enumerate(trace_names):
    trace_id = str(uuid.uuid4())
    ts = day + timedelta(hours=i * 8, minutes=random.randint(0, 59))
    model = random.choice(models)
    agent = random.choice(agents)
    session = random.choice(sessions)
    input_tokens = random.randint(200, 3000)
    output_tokens = random.randint(100, 2500)
    latency_ms = random.randint(200, 5000)
    input_cost = round(input_tokens * model["input_price"], 8)
    output_cost = round(output_tokens * model["output_price"], 8)

    api('POST', '/api/public/traces', {
        "id": trace_id, "name": name,
        "input": f"Task: {name}", "output": f"Completed {name}",
        "sessionId": session,
        "metadata": {"agent": agent, "model": model["name"]},
        "tags": [agent, "production"],
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    })

    api('POST', '/api/public/generations', {
        "traceId": trace_id, "name": f"{name}-llm",
        "model": model["name"],
        "modelParameters": {"temperature": 0.7, "maxTokens": 2048},
        "input": f"Prompt for {name}", "output": f"Response for {name}",
        "usage": {"input": input_tokens, "output": output_tokens, "total": input_tokens + output_tokens},
        "cost": {"input": input_cost, "output": output_cost, "total": round(input_cost + output_cost, 8)},
        "startTime": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endTime": (ts + timedelta(milliseconds=latency_ms)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    })

    for score_name in random.sample(score_names, 2):
        val = round(random.uniform(0.3, 1.0), 2)
        api('POST', '/api/public/scores', {
            "traceId": trace_id, "name": score_name, "value": val,
            "comment": f"Auto-evaluated: {val:.0%}",
        })

    if (i+1) % 5 == 0:
        print(f"  ✅ {i+1}/{len(trace_names)}")

print(f"\nDone! http://localhost:3000")
