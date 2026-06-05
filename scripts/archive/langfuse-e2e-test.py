#!/usr/bin/env python3
"""End-to-end Langfuse trace test."""
import os, sys, time

os.environ['HERMES_LANGFUSE_BASE_URL'] = 'http://localhost:3000'

# Read actual secret key from langfuse .env file
# Example: replace with your own path to the .env file
env_path = os.path.expanduser('~/langfuse/.env')
with open(env_path, 'r') as f:
    for line in f:
        if 'LANGFUSE_INIT_PROJECT_SECRET_KEY' in line:
            sk = line.strip().split('=', 1)[1]
            break

os.environ['HERMES_LANGFUSE_SECRET_KEY'] = sk
os.environ['HERMES_LANGFUSE_PUBLIC_KEY'] = 'pk-lf-QQruh3wQ0dqoMzIzCkYjpNmtS5rlIXnP'

from langfuse import Langfuse

client = Langfuse(
    public_key='pk-lf-QQruh3wQ0dqoMzIzCkYjpNmtS5rlIXnP',
    secret_key=sk,
    base_url='http://localhost:3000',
    debug=True,
)

print("Creating test trace...")
trace_id = client.create_trace_id(seed='hermes-e2e-test')
print(f"Trace ID: {trace_id}")

with client.start_as_current_observation(
    name="E2E Test",
    as_type="chain",
    input="test input",
    metadata={"test": True, "source": "hermes"},
    end_on_exit=True,
) as span:
    span.set_trace_io(input="test input")
    print("Span created")

print("Flushing...")
client.flush()
print("Waiting for flush...")
time.sleep(3)
print("Done! Now checking API...")

# Check API
import urllib.request
from base64 import b64encode
auth = b64encode(f"pk-lf-QQruh3wQ0dqoMzIzCkYjpNmtS5rlIXnP:{sk}".encode()).decode()
req = urllib.request.Request(
    "http://localhost:3000/api/public/traces?limit=10",
    headers={"Authorization": f"Basic {auth}"}
)
resp = urllib.request.urlopen(req, timeout=10)
import json
data = json.loads(resp.read())
traces = data.get('data', [])
print(f"\nTraces in Langfuse: {len(traces)}")
for t in traces[:5]:
    print(f"  [{t.get('timestamp','?')[:19]}] {t.get('name','?')} (id: {t.get('id','?')[:20]}...)")
