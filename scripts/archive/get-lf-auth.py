#!/usr/bin/env python3
"""Get Langfuse basic auth header."""
import base64
pk = sk = None
with open('/Users/luke/langfuse/.env') as f:
    for line in f:
        line = line.strip()
        if 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY=' in line:
            pk = line.split('=', 1)[1]
        elif 'LANGFUSE_INIT_PROJECT_SECRET_KEY=' in line:
            sk = line.split('=', 1)[1]
auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
print(auth)
