#!/usr/bin/env python3
"""Get Langfuse basic auth header."""
import base64, os
pk = sk = None
# Example: replace with your own path to the .env file
env_path = os.path.expanduser('~/langfuse/.env')
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY=' in line:
            pk = line.split('=', 1)[1]
        elif 'LANGFUSE_INIT_PROJECT_SECRET_KEY=' in line:
            sk = line.split('=', 1)[1]
auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
print(auth)
