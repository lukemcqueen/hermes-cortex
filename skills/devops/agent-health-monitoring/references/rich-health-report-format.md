# Rich Health-Report Format — Inbox Push Agents

Some agents (like Titus on macOS) push a **rich JSON health report** to the inbox instead of a compact health vector. This format carries services, issues, resources, uptime, and other metadata — not just a 9-element binary vector.

## The Two Push Formats

| Format | Structure | Agents | Handler |
|--------|-----------|--------|---------|
| **Compact vector** | `{"v": [1,1,...], "h": "t", "t": 1782882578}` | Server agents via `health-vector.py --serve` | `_parse_vector_body()` — direct passthrough |
| **Rich health-report** | `{"type": "health-report", "services": [...], "issues": [...], ...}` | Client-only agents (Titus) via `health-vector-push.sh` | `_parse_rich_report()` — converts to vector + preserves `_rich` metadata |

## Rich Health-Report JSON Schema

```json
{
  "type": "health-report",
  "agent": "LAM2",
  "healthy": false,
  "reachable": true,
  "server": "LAM2",
  "hostname": "LAM2",
  "timestamp": "2026-06-17T07:44:22.662706+00:00",
  "issues": [
    {
      "severity": "high",
      "check": "cron_health",
      "detail": "Errored cron: service-recovery",
      "cron": "service-recovery"
    }
  ],
  "issue_count": 2,
  "critical_count": 0,
  "services": [
    {"name": "nginx", "status": "running", "pid": 765},
    {"name": "ollama", "status": "unknown", "pid": null},
    {"name": "gbrain", "status": "running", "pid": 52945},
    {"name": "agent_inbox", "status": "running", "pid": 60569}
  ],
  "service_summary": "3/4 up",
  "uptime_seconds": 200,
  "resources": {
    "cpu_percent": 295.3,
    "load_avg": [5.31, 5.82, 5.96],
    "memory_percent": 59,
    "disk_percent": 13
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"health-report"` | Yes | Discriminator — tells parser this is not a compact vector |
| `healthy` | `bool` | Yes | Overall health summary by the agent itself |
| `reachable` | `bool` | Yes | Whether the agent considers itself reachable |
| `hostname` / `agent` / `server` | `str` | At least one | Identifies the agent machine |
| `issues` | `array` | No | List of issue objects (see below) |
| `issue_count` / `critical_count` | `int` | No | Pre-computed counts |
| `services` | `array` | No | List of service objects with `name`, `status`, `pid` |
| `service_summary` | `str` | No | Human-readable summary like `"3/4 up"` |
| `uptime_seconds` | `int` | No | Agent uptime in seconds |
| `resources` | `object` | No | CPU, memory, disk metrics |

### Issue object

```json
{
  "severity": "high | warning | info",
  "check": "cron_health | nginx | ...",
  "detail": "Human-readable description",
  "cron": "cron-job-name"   // optional, for cron_health checks
}
```

### Service object

```json
{
  "name": "nginx | ollama | gbrain | agent_inbox | ...",
  "status": "running | unknown | stopped | down | up",
  "pid": 765
}
```

## Conversion: Rich Report → 9-Element Vector

`_parse_rich_report()` in `orch-health-report.py` maps the rich format to the standard 9-element `SERVICE_MAP`:

| Index | SERVICE_MAP entry | Source from rich report |
|-------|-------------------|------------------------|
| 0 | resources | `1` if `resources` object is non-empty |
| 1 | services | `1` if `services` array is non-empty |
| 2 | no_errored_crons | `-1` if any issue has `"errored"` in its detail |
| 3 | no_stale_crons | `-1` if any issue has `"stale"` in its detail |
| 4 | nginx | Direct match from `services[].name == "nginx"` |
| 5 | ollama | Direct match from `services[].name == "ollama"` |
| 6 | gbrain | Direct match from `services[].name == "gbrain"` |
| 7 | disk_ok | `-1` if `resources.disk_percent >= 90` |
| 8 | gbrain_sources_ok | `1` if gbrain status is running/up |

Service status mapping: `running/up` → `1`, `down/stopped` → `-1`, anything else → `0`.

## Preservation: `_rich` Metadata

After conversion, the full rich data is preserved under a `_rich` key in the result dict:

```python
result = {
    "v": [1, 1, -1, -1, 1, 0, 1, 1, 1],  # standard vector
    "h": "LAM2",                             # hostname
    "t": int(time.time()),                  # timestamp
    "_rich": {
        "issues": [...],       # original issue objects
        "services_raw": [...], # original service objects  
        "resources": {...},    # original resource metrics
        "uptime_seconds": 200,
        "service_summary": "3/4 up",
        "issue_count": 2,
        "critical_count": 0,
    }
}
```

`_build_structured_data()` uses `_rich` when available instead of the vector-derived data, providing the dashboard with real service names, issue details, uptime, and resource metrics.

## Pitfalls

- **Compact vector push vs rich report:** If a client agent switches push scripts, the orchestrator silently sees "no health message in inbox" because `_parse_vector_body()` doesn't recognize the new format. Always check the actual body from the inbox before assuming the format.
- **Service name mismatch:** The rich report uses different service names (`agent_inbox`) than the SERVICE_MAP (`nginx`, `ollama`, `gbrain`). Services not in the SERVICE_MAP are preserved in `_rich` but don't appear in the vector — the dashboard still shows them via the rich path.
- **severity != critical:** Titus uses `"high"` and `"warning"` as severity levels, not `"critical"`. The issue count is preserved but the severity string is passed through as-is. The dashboard treats `"critical"` specially (red left border) — non-critical issues show as degraded (yellow border).
