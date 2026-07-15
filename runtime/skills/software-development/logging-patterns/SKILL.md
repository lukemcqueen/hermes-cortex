---
name: logging-patterns
version: 1.0.0
category: software-development
description: >
  Structured logging conventions: log levels, format standards, context
  injection, correlation IDs, sensitive data scrubbing, and rotation.
  Applies to Python, Node.js, shell scripts, and infrastructure.
tags: [logging, observability, debugging, structured-logging, production]
related_skills: [systematic-debugging, linux-performance-diagnostics, engineering-approach]
---

# Logging Patterns

## When to Use

Load this skill when:
- Adding logging to a new service or script
- Diagnosing a production issue from logs
- Reviewing code for logging correctness
- Setting up log aggregation or rotation

## Core Principles

### 1. Structured Over Unstructured

**Bad (unstructured — grep-unfriendly):**
```python
logger.info(f"User {user_id} logged in from {ip}")
```

**Good (structured — queryable):**
```python
logger.info("user_login", extra={"user_id": user_id, "ip": ip, "method": "oauth"})
```

**Best (JSON-structured — ELK/Loki ready):**
```python
logger.info({"event": "user_login", "user_id": user_id, "ip": ip, "method": "oauth"})
```

Structure enables: `grep user_login | jq 'select(.method == "oauth")'`.

#### Python Libraries

| Library | When to use |
|---------|-------------|
| `structlog` | **Recommended** for new projects — wraps stdlib, auto-injects context, JSON output by default, middleware for FastAPI |
| `python-json-logger` | Lightweight — adds JSON formatting to stdlib with minimal config |
| `loguru` | Simple — zero-config, colored console, easy rotation. Less structured than structlog |
| `stdlib logging` + `dictConfig` | When you can't add dependencies — configure via YAML dictionary |

**structlog example (recommended):**
```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
logger.info("user_login", user_id=user_id, ip=ip, method="oauth")
```

**dictConfig YAML template (stdlib):**
```yaml
version: 1
formatters:
  json:
    format: "%(asctime)s %(levelname)s %(name)s %(message)s"
    class: pythonjsonlogger.jsonlogger.JsonFormatter
handlers:
  console:
    class: logging.StreamHandler
    formatter: json
    stream: ext://sys.stdout
  file:
    class: logging.handlers.RotatingFileHandler
    formatter: json
    filename: /var/log/app.json
    maxBytes: 10485760  # 10MB
    backupCount: 5
root:
  level: INFO
  handlers: [console, file]
```

### 2. Field Schema Standards

Align with **Elastic Common Schema (ECS)** or **OpenTelemetry** semantic conventions for interoperability with observability platforms.

**Standard field names:**
```json
{
    "@timestamp": "2026-07-15T14:30:00.000Z",
    "log.level": "INFO",
    "event.action": "user_login",
    "service.name": "api-gateway",
    "service.version": "1.2.3",
    "trace.id": "abc123def456",
    "span.id": "span789",
    "user.id": "user_42",
    "client.ip": "203.0.113.42",
    "duration.ms": 342,
    "error.type": "ConnectionRefusedError",
    "error.message": "Connection refused: db:5432"
}
```

| Field | ECS name | Required | Example |
|-------|----------|----------|---------|
| Timestamp | `@timestamp` | Always | RFC3339 UTC |
| Log level | `log.level` | Always | `INFO`, `ERROR` |
| Event name | `event.action` | Always | `payment_processed` |
| Service name | `service.name` | Always | `api-gateway` |
| Service version | `service.version` | Deploy | `1.2.3` |
| Trace ID | `trace.id` | Request ctx | `abc123` |
| Duration | `duration.ms` | Perf-relevant | `342` |
| Error type | `error.type` | On failure | `ConnectionRefusedError` |
| Error message | `error.message` | On failure | `Connection refused: db:5432` |

**Rule of thumb:** If a human wouldn't care about it in production, it's `DEBUG`.
If a human needs to act on it, it's `ERROR` or `CRITICAL`.

### 3. What Every Log Entry Should Contain

| Field | Required | Example |
|-------|----------|---------|
| `timestamp` | Always | `2026-07-15T14:30:00Z` (RFC3339, UTC) |
| `level` | Always | `INFO`, `ERROR` |
| `event`/`message` | Always | `payment_processed`, `Connection timeout` |
| `service`/`component` | Always | `api-gateway`, `cron-scheduler` |
| `trace_id` | Request context | `req-abc123` |
| `duration_ms` | Performance-relevant | `342` |
| `error` | On failure | `ConnectionRefusedError(61)` |

### 4. Correlation IDs

Every request or task gets a single ID that propagates across services:

```python
import uuid
request_id = str(uuid.uuid4())  # req_abc123def456
```

**Propagation:**
- HTTP: `X-Request-ID` header
- Message queues: metadata field on each message
- Logging: inject into `extra` on every log call
- Error responses: return to caller as `X-Request-ID` header

```python
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(threading.current_thread(), 'request_id', 'none')
        return True

logging.getLogger().addFilter(RequestIdFilter())
```

### 5. Sensitive Data Scrubbing

**NEVER log:** passwords, tokens, API keys, PII (email, phone, SSN), credit
card numbers, session cookies.

**Pattern: sanitize before logging:**
```python
def sanitize_for_log(data: dict) -> dict:
    """Return a copy with sensitive fields redacted."""
    sensitive_keys = {"password", "token", "secret", "authorization", "cookie", "ssn"}
    return {k: ("[REDACTED]" if k.lower() in sensitive_keys else v) for k, v in data.items()}
```

**For URLs:**
```python
import re
url = re.sub(r'(token|api_key|secret)=\w+', r'\1=[REDACTED]', url)
```

### 6. Error Logging Pattern

```python
try:
    result = external_api_call()
    logger.info("external_api_success", extra={"endpoint": endpoint, "duration_ms": duration})
except TimeoutError:
    logger.warning("external_api_timeout", extra={"endpoint": endpoint, "timeout_s": timeout})
    raise  # Let caller decide retry strategy
except Exception as e:
    logger.error("external_api_failed",
        extra={"endpoint": endpoint, "error": str(e), "error_type": type(e).__name__})
    raise  # Re-raise for caller handling
```

**Don't log-and-pass.** Either log and re-raise, or let the caller log.
Double-logging creates noise and hides the error's origin.

### 7. Startup / Shutdown Logging

Every service MUST log:
- **Startup:** version, config path, listen address, DB connection status
- **Shutdown:** reason (SIGTERM, crash, graceful), uptime, final stats

```python
logger.info("service_starting", extra={"version": __version__, "listen": ":8080", "db": "connected"})
# ... later ...
logger.info("service_stopping", extra={"uptime_s": time.time() - start_time, "reason": "SIGTERM"})
```

### 8. Shell Script Logging

```bash
#!/usr/bin/env bash
set -euo pipefail

log() {
    local level="$1"
    shift
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [$level] $*" >&2
}

log_info()  { log "INFO" "$@"; }
log_error() { log "ERROR" "$@"; }

log_info "Starting backup: target=$BACKUP_DIR"
# ... work ...
log_info "Backup complete: size=$(du -sh "$BACKUP_DIR")"
```

### 9. Log Rotation

| Platform | Tool | Config location |
|----------|------|-----------------|
| Linux (systemd) | `logrotate` | `/etc/logrotate.d/` |
| macOS | `newsyslog` | `/etc/newsyslog.d/` or `launchd` |
| Docker | Docker logging driver | `--log-opt max-size=10m --log-opt max-file=3` |
| Python | `RotatingFileHandler` | In code, maxBytes=10MB, backupCount=5 |

**logrotate example:**
```bash
/var/log/myapp/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

## Anti-Patterns

| Anti-pattern | Why it's wrong |
|------|-------|
| `print()` in production | No levels, no structure, no timestamp, no rotation |
| Log-and-pass (log then continue) | Error is visible but unhandled — worst of both worlds |
| Logging in tight loops | `for item in 10000_items: logger.debug(...)` = log spam |
| Logging secrets | Passwords in logs = security incident |
| No correlation IDs | Can't trace a request across services |
| `except: pass` with no log | Error swallowed silently — undebuggable |
| Different format per service | Every team has its own schema — can't aggregate |

## Verification

```python
# Check log output is valid JSON
python3 -c "
import json, sys
for line in sys.stdin:
    try:
        obj = json.loads(line)
        assert 'timestamp' in obj
        assert 'level' in obj
        assert 'event' in obj or 'message' in obj
    except (json.JSONDecodeError, AssertionError) as e:
        print(f'Invalid log line: {e}', file=sys.stderr)
        sys.exit(1)
print('All log lines valid')
" < /var/log/myapp/current.log
```
