# 🏗️ Enterprise Agentic Patterns — What You Can Take

> **🪪 Scope:** This document serves two audiences:
> - **General developers** — everything unmarked is universal guidance you can
>   copy into your own agentic system.
> - **Luke's deployment** — sections marked with `⚡` show how these patterns
>   are used in a specific multi-agent fleet (Moses orchestrator, peer agents,
>   KST timezone, Telegram delivery). Treat those as concrete examples to
>   adapt, not requirements.
>
> Every pattern below names the **exact file** in this repo that implements it,
> so you can read the real code, not a summary.

This repo is a working **enterprise-grade agentic harness** — a multi-agent
fleet with enforced change governance, self-healing operations, and a deep
offline knowledge stack. This document distills the reusable patterns into
take-away pieces. Want to build agents that talk to each other, cut LLM
token spend, or stop attackers? Start here.

---

## 1. 🛡️ A Ready-Made Bad-Actor IP Blocklist (4,233 IPs)

**Take-away:** a cumulative, evidence-based blocklist you can drop into your
own nginx/fail2ban setup today.

| Asset | Location |
|---|---|
| Blocklist (IPv4) | [`ops/install/deploy/nginx/blocked_ips.add`](../ops/install/deploy/nginx/blocked_ips.add) — 4,233 IPs, one per line |
| Submission queue | [`ops/install/deploy/nginx/blocked_ips.submit`](../ops/install/deploy/nginx/blocked_ips.submit) — agents append candidate IPs |
| Generator | [`ops/install/deploy/nginx/generate-blocked-ips.py`](../ops/install/deploy/nginx/generate-blocked-ips.py) |
| Deployer | [`ops/scripts/manage/deploy-blocked-ips.sh`](../ops/scripts/manage/deploy-blocked-ips.sh) |

**How it works:** the blocklist is **append-only and cumulative** — every agent
in the fleet contributes IPs it has seen attacking (via the threat pipeline,
see §6). Entries are plain IPv4/IPv6, one per line, so you can consume them
with `grep -Ff blocked_ips.add` in nginx `deny` directives, fail2ban
`ignoreip`/`banip` lists, or UFW rules.

**Read it yourself:**
```bash
head -20 ops/install/deploy/nginx/blocked_ips.add        # see the format
wc -l ops/install/deploy/nginx/blocked_ips.add            # 4,233 entries
```

**Deploy to nginx (example):**
```nginx
# inside a server or http block
include /etc/nginx/blocked_ips.conf;
```
```bash
# generate the include file from the list
awk '{print "deny " $0 ";"}' blocked_ips.add > blocked_ips.conf
```

---

## 2. 🤝 Agent-to-Agent Messaging (PGMQ Bus, A2A Protocol)

**Take-away:** a full, production-proven Agent-to-Agent (A2A) messaging layer
built on Postgres PGMQ — no Kafka, no Redis, no shared state.

| Asset | Location |
|---|---|
| Bus library (HTTP wrapper) | [`ops/scripts/lib/cortex_bus.py`](../ops/scripts/lib/cortex_bus.py) — 381 lines, zero deps |
| Message handler (agent-side poller) | [`ops/scripts/agent/agent-message-handler.py`](../ops/scripts/agent/agent-message-handler.py) |
| Update protocol (REQUEST/RESULT) | [`docs/fleet-update-protocol.md`](fleet-update-protocol.md) |
| Bus architecture | [`docs/architecture.md`](architecture.md) |

**The pattern:** each agent owns an inbox queue (`inbox_<agent>`); it polls
every 5 minutes, processes structured messages (`UPDATE_REQUEST`,
`ROLLBACK_REQUEST`, `GIT_AUTH_CHECK`), and posts results back to the sender's
queue. Messages carry `correlation_id` for request/response matching.

**Minimal send/read (the whole API):**
```python
from cortex_bus import bus_send, bus_read, bus_archive

# send a message to another agent's inbox
bus_send("inbox_worker", {
    "from": "orchestrator",
    "to": "worker",
    "subject": "UPDATE_REQUEST",
    "correlation_id": "req-123",
    "body": {"target_sha": "abc123"},
})

# read one message from your own inbox (60s visibility timeout)
msg = bus_read("inbox_worker", vt=60)
if msg:
    # ... do the work ...
    bus_archive("inbox_worker", msg["msg_id"])  # ack
```

**Key design decisions worth copying:**
- **PGMQ, not a bespoke broker** — Postgres is already deployed; PGMQ gives
  you at-least-once queues with visibility timeouts for free.
- **Correlation IDs on every message** — makes request/response trivially
  matchable and enables the fleet rollback protocol.
- **Heartbeat/liveness** — `bus_health()` and per-agent health pushes let an
  orchestrator detect a dead agent without pinging it.
- **No shared mutable state** — agents coordinate only through queues.

---

## 3. 💰 RAG / Semantic Caching to Cut Token Cost

**Take-away:** three layers of retrieval that answer queries **before** the
LLM ever sees them — cutting API spend and enabling offline operation.

### Layer 1 — Semantic Web Cache (sqlite-vec + Ollama)

| Asset | Location |
|---|---|
| Web cache | [`ops/web-cache/web_cache.py`](../ops/web-cache/web_cache.py) |

**The pattern:** `web_search`/`web_extract` results are stored locally in a
SQLite database with **sqlite-vec** vector indexes, embedded by local Ollama
(`nomic-embed-text:v1.5`, 768-dim). Repeated queries hit the cache instead of
the network/LLM:

```bash
web_cache search "<query>"          # semantic search of cached results
web_cache auto "<query>"            # search + store (agent-friendly)
web_cache stats                     # hit rate, size
web_cache export backup.tar.gz      # portable, shareable cache
```

Agents query the cache **first**; only a miss goes to the live API. Because
the cache is portable (`export`/`import`), a whole team can share one
curated knowledge base.

### Layer 2 — mycortex: Postgres Knowledge Brain

| Asset | Location |
|---|---|
| Design | [`docs/design/mycortex-DESIGN.md`](design/mycortex-DESIGN.md) |
| Multi-tenancy | [`docs/design/mycortex-multi-tenancy.md`](design/mycortex-multi-tenancy.md) |
| CLI plugin | `plugins/mycortex-command` |

**The pattern:** git repos are the source of truth; a cron syncs them into a
shared Postgres index (FTS + `pg_texample` fuzzy search + pgvector semantic
slice). **Multi-tenant by construction** — each profile connects as its own
`mycortex_reader_<profile>` Postgres role, and Row-Level Security keyed on
`CURRENT_USER` isolates tenants with zero policy changes.

```bash
# after install: sync repos into the index, then query
agent-mycortex-sync            # 15-min cron
mycortex search "how do I..."  # FTS + fuzzy + semantic
```

### Layer 3 — Full offline cascade

```
Agent query → web_cache (50μs) → kiwix ZIM (localhost:8080) → mycortex (RAG) → LLM (always)
```

See [`docs/knowledge-isolation-architecture.md`](knowledge-isolation-architecture.md) and
[`ops/offline/`](../ops/offline/) for the offline code corpus
(520+ snippets, 55 topics, 30+ languages) and offline reader.

---

## 4. 🔒 Enforced Change Governance (Loop Governance)

**Take-away:** change discipline enforced **at the tool level**, not
suggested. Write tools physically block without an active, scored cycle.

| Asset | Location |
|---|---|
| Enforcer plugin | `plugins/governance-enforcer/` |
| MCP server | `mcp-servers/loop-gov-mcp.py` |
| Reference | [`docs/loop-governance-reference.md`](loop-governance-reference.md) |

**The cycle:**
```
begin_change() → work → cycle_query() → feedback_accept() → end_change()
```

**Why it's enterprise-grade:**
- **Three enforcement layers** — MCP tool gate (blocks `patch`/`write_file`/
  `terminal` without a lock), pre-commit hook (auto-scores the diff, runs
  adversarial verification), cron auditor (catches unscored changes, cleans
  stale locks).
- **No bypass** — `SKIP_SCORE=1` and `--no-verify` are logged and audited,
  not honored silently.
- **TDD Iron Law** — new prod-code files must ship with a test file in the
  same commit (structural gate).
- **Adversarial verification** — every staged script is fuzz-checked against
  attack patterns before commit (A2 default, A4 for security/hook files).

---

## 5. 🤖 Self-Healing Operations (Auto-Remediation)

**Take-away:** a sensor → marker → fixer pipeline that repairs crashes before
a human wakes up.

| Asset | Location |
|---|---|
| Sensor | `ops/scripts/remediation/` (sensor scans) |
| Fixer crons | `agent-fixer-workday/evening/overnight` |
| Reference | [`docs/fleet-reference.md`](fleet-reference.md) |

**The pattern:**
```
remediation-sensor → remediation markers → agent-remediate-apply → agent-fixer
```
Sensors detect problems (crashed service, broken config, stale lock), write a
remediation marker, and a specialized fixer agent applies the cure. Every
fix is governed (same loop-governance cycle), so automation can't bypass
change discipline.

---

## 6. 🕵️ Threat Detection & IP Submission Pipeline

**Take-away:** a daily pipeline that turns nginx logs into **new blocklist
entries**, closing the loop between attack and defense.

| Asset | Location |
|---|---|
| Pipeline | [`ops/scripts/manage/agent-nginx-threat-pipeline.sh`](../ops/scripts/manage/agent-nginx-threat-pipeline.sh) |
| Classifier (evidence-based review) | [`ops/scripts/manage/classify-blocked-ips.sh`](../ops/scripts/manage/classify-blocked-ips.sh) |
| Blocklist fixer | [`ops/install/deploy/nginx/fix-blocked-ips.py`](../ops/install/deploy/nginx/fix-blocked-ips.py) |

**Flow:** scan nginx access/error logs for attack patterns → collect
fail2ban bans → append new IPs to `blocked_ips.submit` → promote to
`blocked_ips.add` → deploy fleet-wide. The classifier keeps it evidence-based
(no false-positive mass bans; see the DDoS-relaxation runbook in `docs/runbooks/`).

---

## 7. 📦 Ready-to-Read Implementation Files

The fastest way to learn these patterns is the source. Suggested reading
order:

| Want to understand... | Read |
|---|---|
| A2A messaging end-to-end | `ops/scripts/lib/cortex_bus.py` + `docs/fleet-update-protocol.md` |
| Token-cost caching | `ops/web-cache/web_cache.py` (400 lines, self-contained) |
| Enforced governance | `mcp-servers/loop-gov-mcp.py` + `docs/loop-governance-reference.md` |
| Self-healing | `ops/scripts/remediation/` sensors + `agent-fixer-*` crons |
| Bad-actor defense | `blocked_ips.add` + `agent-nginx-threat-pipeline.sh` |

---

> **⚡ Luke's deployment:** In the production fleet, these patterns run across
> six agents (orchestrators Moses/Esther, server agents Joseph/Kustos/Gisu,
> dev agent Titus) with Telegram delivery and KST schedules. The repo itself
> stays neutral — agent names, hostnames, and schedules are deployment
> details, not part of the framework. The patterns above are the framework.
