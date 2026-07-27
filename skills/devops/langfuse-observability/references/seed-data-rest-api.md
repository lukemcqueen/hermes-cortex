# Seed Data via REST API

When the Langfuse SDK is unavailable or having version conflicts, push traces directly via the REST API.

## Authentication

Langfuse API uses HTTP Basic Auth with `public_key:secret_key`:

```python
import base64
auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
headers = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}
```

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/public/traces` | POST | Create a trace |
| `/api/public/generations` | POST | Add an LLM generation to a trace |
| `/api/public/spans` | POST | Add a non-LLM span to a trace |
| `/api/public/scores` | POST | Add a score to a trace |
| `/api/public/ingestion` | POST | Batch ingestion (multiple events in one call) |

## Required parameters (fromTimestamp)

The GET `/api/public/traces` endpoint requires `fromTimestamp`:

```bash
curl -u "pk:sk" "http://localhost:3000/api/public/traces?limit=10&fromTimestamp=2026-06-01T00:00:00.000Z"
```

## Trace creation

```python
import requests, json

r = requests.post(
    'http://localhost:3000/api/public/traces',
    auth=(pk, sk),
    json={
        'name': 'trace-name',
        'sessionId': 'sess-001',
        'userId': 'agent-name',
        'metadata': {'source': 'seed'},
        'tags': ['tag1', 'tag2'],
        'input': 'User request text',
        'output': 'Assistant response text',
    }
)
trace_id = r.json()['id']
```

## Generation creation (inside a trace)

```python
r = requests.post(
    'http://localhost:3000/api/public/generations',
    auth=(pk, sk),
    json={
        'traceId': trace_id,
        'name': 'model-name',
        'model': 'gpt-4o-mini',
        'modelParameters': {'temperature': 0.7, 'max_tokens': 1024},
        'input': 'Full prompt text',
        'output': 'Full completion text',
        'usage': {'input': 42, 'output': 85, 'unit': 'TOKENS'},
        'startTime': '2026-06-30T00:00:00.000Z',
        'endTime': '2026-06-30T00:00:01.000Z',
    }
)
```

## Span creation (for non-LLM operations)

```python
r = requests.post(
    'http://localhost:3000/api/public/spans',
    auth=(pk, sk),
    json={
        'traceId': trace_id,
        'name': 'docker-health',
        'input': {'command': 'docker ps'},
        'output': {'healthy': 12},
        'startTime': '2026-06-30T00:00:00.000Z',
        'endTime': '2026-06-30T00:00:01.000Z',
    }
)
```

## Score creation

```python
r = requests.post(
    'http://localhost:3000/api/public/scores',
    auth=(pk, sk),
    json={
        'traceId': trace_id,
        'name': 'helpfulness',
        'value': 0.95,
        'comment': 'Accurate summary',
    }
)
```

## Timing

Timestamps must be ISO 8601 in UTC:
```python
time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
```

## Propagation delay

After posting, wait 2-3 seconds for ClickHouse ingestion before reading back.

## Limitation

The REST API creates traces but they may not trigger all Langfuse analytics processing (cost calculation, model registry). For full fidelity, use the SDK's OTLP export path. The REST API is ideal for demos and seed data.