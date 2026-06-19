#!/usr/bin/env python3
"""Test MinIO and S3 access."""
import os
import urllib.request
import json

# Test MinIO health
try:
    req = urllib.request.Request("http://localhost:9090/minio/health/live")
    resp = urllib.request.urlopen(req, timeout=5)
    print(f"MinIO health: {resp.status}")
except Exception as e:
    print(f"MinIO health failed: {e}")

# Read minio root creds
# Example: replace with your own path to the .env file
env_path = os.path.expanduser('~/langfuse/.env')
with open(env_path, 'rb') as f:
    content = f.read()

minio_pass = None
for line in content.split(b'\n'):
    prefix = b'MINIO_ROOT_PASSWORD='
    if line.startswith(prefix):
        minio_pass = line[len(prefix):].decode()
        print(f"MinIO root password: len={len(minio_pass)}")
        break

s3_event_secret = None
for line in content.split(b'\n'):
    prefix = b'LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY='
    if line.startswith(prefix):
        s3_event_secret = line[len(prefix):].decode()
        print(f"S3 event secret: len={len(s3_event_secret)}")
        break

print(f"Credentials match: {minio_pass == s3_event_secret}")

# Check Langfuse OTLP endpoint
try:
    import base64
    # Use the Langfuse project keys for auth
    # Example: replace with your own path to the .env file
    with open(env_path, 'rb') as f:
        content = f.read()
    pk = None
    sk = None
    for line in content.split(b'\n'):
        if line.startswith(b'LANGFUSE_INIT_PROJECT_PUBLIC_KEY='):
            pk = line.split(b'=', 1)[1].decode()
        if line.startswith(b'LANGFUSE_INIT_PROJECT_SECRET_KEY='):
            sk = line.split(b'=', 1)[1].decode()
    
    if pk and sk:
        auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        req = urllib.request.Request(
            "http://localhost:3000/api/public/traces?limit=5",
            headers={"Authorization": f"Basic {auth}"}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        print(f"\nLangfuse traces: {data.get('meta',{}).get('totalItems',0)}")
    else:
        print("\nCould not read project keys")
except Exception as e:
    print(f"\nLangfuse API error: {e}")
