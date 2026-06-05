---
language: python
tags: [util, net, pattern]
title: Retry Decorator
description: Decorator to retry a function with exponential backoff on failure.
source: pattern
---

```python
import time
import functools

def retry(max_attempts=3, delay=1, backoff=2, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            wait = delay
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(wait)
                    wait *= backoff
            return None
        return wrapper
    return decorator

@retry(max_attempts=5, delay=0.5)
def fetch_data(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.read()
```
