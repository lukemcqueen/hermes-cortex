#!/usr/bin/env python3
"""bus-inbox-inspect.py — re-runnable Agent Bus inbox-tick inspection.

Emits a JSON transcript to stdout covering, for BOTH the local bus
(127.0.0.1:8903) and the primary/peer bus (CORTEX_BUS_URL):
  - every queue with depth/processing flags (non-empty or DLQ)
  - DLQ depth for every *_dlq queue
  - contents of inbox_<agent>, inbox_orchestrator, out_<agent>, inbox_health_check
  - forwarder last_run (state file)
  - failover status (state file)

Usage: python3 bus-inbox-inspect.py [agent_name]
Read-only: uses /api/pgmq/queues and /api/pgmq/peek only — never consumes, never
writes, never archives. Safe to run from a cron tick.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCAL_URL = "http://127.0.0.1:8903"
STATE = Path.home() / ".hermes-cortex" / "state"
CONFIG_FILE = Path.home() / "hermes-cortex" / ".env"
PEEK_QUEUES = ("inbox_{agent}", "inbox_orchestrator", "out_{agent}", "inbox_health_check")
# Peek is a window, not the full queue: the API returns at most PEEK_LIMIT
# messages. A backlog larger than the window is never hidden — the exact depth
# is always reported by summarize_queues() from /api/pgmq/queues.
PEEK_LIMIT = 200
# A pending message older than this in ANY queue is a real issue (a stuck
# message nobody is draining), regardless of which queue it sits in. Fresh
# pipeline traffic (mirrors, health reports) is minutes old and never trips it.
STALE_HOURS = 24
# A queued message at/above this bus priority (0-100, int) is 'urgent' and is
# reported even when fresh.
URGENT_PRIORITY = 50


def _read_config(key: str) -> str:
    """Read a KEY=value from the canonical cortex .env (env wins)."""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                v = line.split("=", 1)[1].strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                return v
    except OSError:
        pass
    return ""


def _load_config() -> tuple[str, str, str]:
    """(primary_bus_url, bearer_token, basic_auth) from env → ~/hermes-cortex/.env."""
    url = _read_config("CORTEX_BUS_URL") or LOCAL_URL
    token = _read_config("CORTEX_BUS_TOKEN")
    basic = _read_config("CORTEX_BASIC_AUTH") or _read_config("CORTEX_BUS_AUTH")
    return url, token, basic


def _auth_headers(scheme: str) -> dict:
    _, token, basic = _load_config()
    if scheme == "bearer" and token:
        return {"Authorization": "Bearer " + token}
    if scheme == "basic" and basic:
        return {"Authorization": "Basic " + base64.b64encode(basic.encode()).decode()}
    return {}


def _http_get(base: str, path: str) -> dict:
    last = None
    for scheme in ("bearer", "basic"):
        headers = _auth_headers(scheme)
        if not headers:
            continue
        try:
            req = urllib.request.Request(base + path, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = {"_http_error": e.code, "_scheme": scheme}
            if e.code not in (401, 403):
                return last
        except Exception as e:  # noqa: BLE001
            last = {"_error": str(e), "_scheme": scheme}
    return last or {"_error": "no credentials available"}


def _norm(body):
    """Unwrap the bus's nested body shapes (JSON-string, and legacy `raw`)."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:  # noqa: BLE001
            pass
    if isinstance(body, dict) and isinstance(body.get("raw"), str):
        try:
            body = json.loads(body["raw"])
        except Exception:  # noqa: BLE001
            pass
    return body


def _msg_entry(m: dict) -> dict:
    body = _norm(m.get("body"))
    entry = {"msg_id": m.get("msg_id"), "enqueued_at": m.get("enqueued_at"),
             "read_ct": m.get("read_ct")}
    if isinstance(body, dict):
        for k in ("from", "to", "subject", "topic", "correlation_id", "priority",
                  "forwarded_from"):
            if k in body:
                entry[k] = body[k]
        inner = body.get("body")
        if isinstance(inner, dict):
            entry["mirrored_from_queue"] = inner.get("mirrored_from_queue")
            entry["primary_msg_id"] = inner.get("primary_msg_id")
        entry["payload"] = (inner if isinstance(inner, str) else json.dumps(inner))[:300] \
            if inner is not None else None
    return entry


def summarize_queues(queue_json: dict) -> dict:
    """Pure: split a /api/pgmq/queues payload into non-empty + DLQ lists."""
    queues = queue_json.get("queues", [])
    return {
        "queue_total": queue_json.get("total", len(queues)),
        "nonempty": [
            {"name": q["name"], "depth": q["depth"], "processing": q["processing"],
             "dlq": q.get("dlq", False), "parent": q.get("parent")}
            for q in queues if q.get("depth") or q.get("processing") or q.get("dlq")
        ],
        "dlq": [
            {"name": q["name"], "depth": q["depth"], "processing": q["processing"]}
            for q in queues if q["name"].endswith("_dlq")
        ],
    }


def inspect(label: str, base: str, agent: str = "esther") -> dict:
    out: dict = {"label": label, "base": base, "inspection_error": None}
    q = _http_get(base, "/api/pgmq/queues")
    if q.get("_http_error") or q.get("_error"):
        # A dead / auth-broken bus MUST NOT be summarized as an empty fleet.
        out["inspection_error"] = f"queue fetch failed: {q}"
        out.update({"queue_total": None, "nonempty": [], "dlq": []})
    else:
        out.update(summarize_queues(q))
    out["peeks"] = {}
    for tmpl in PEEK_QUEUES:
        qn = tmpl.format(agent=agent)
        d = _http_get(base, f"/api/pgmq/peek/{qn}?limit={PEEK_LIMIT}")
        if d.get("_http_error") or d.get("_error"):
            # A forbidden peek (e.g. a DLQ the agent may not read) is not by
            # itself a bus failure — record it, but only the queues fetch above
            # is treated as fatal for 'inspection_error'.
            out["peeks"][qn] = {"error": d}
            continue
        msgs = [_msg_entry(m) for m in d.get("messages", [])]
        out["peeks"][qn] = {"count": len(msgs), "messages": msgs}
    return out


def _state(name: str, keys=None):
    f = STATE / name
    if not f.exists():
        return {"_missing": str(f)}
    try:
        d = json.loads(f.read_text())
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}
    return {k: d.get(k) for k in keys} if keys else d


def build_report(agent: str = "esther", primary_url: str | None = None) -> dict:
    if primary_url is None:
        primary_url, _, _ = _load_config()
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "buses": [inspect("local", LOCAL_URL, agent),
                  inspect("primary", primary_url, agent)],
        "forwarder": _state("bus-forwarder-state.json",
                            ["last_run", "total_forwarded", "total_peer_to_local",
                             "total_local_to_peer"]),
        "failover": _state("bus-failover-state.json"),
    }


def _parse_ts(value):
    """Parse a bus enqueued_at (Postgres 'YYYY-MM-DD HH:MM:SS+00' or ISO)."""
    if not value:
        return None
    t = str(value).strip().replace(" ", "T")
    if t.endswith("+00"):
        t += ":00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fleet_issues(report: dict, now=None) -> list[str]:
    """Actionable bus-health problems in a report; empty == no-action condition.

    This is the runnable statement of the cron's silent policy: the transcript
    is 'clean' (and the tick may stay silent) exactly when this returns [].

    Signal (a real issue):
      * a bus whose inspection FAILED (dead / auth-broken) — never summarize
        that as an empty, clean fleet
      * any DLQ with pending or processing messages (= a BLOCKED message: the
        decoder exhausted max_retries)
      * any queue holding a message older than STALE_HOURS — a stuck pending
        message, whatever queue it sits in (out_*, inbox_orchestrator, ...)
      * any queue holding an URGENT message (priority >= URGENT_PRIORITY), even
        if fresh
      * the agent's OWN inbox (inbox_<agent>) holding unprocessed messages
      * a non-empty queue whose messages could not be dated
      * a forwarder that has never recorded a run
      * an ACTIVE failover

    Mapping to the cron's vocabulary: pending = any dated/stale/undated message;
    urgent = priority >= URGENT_PRIORITY; blocked = a DLQ entry (retries
    exhausted) or a stale pending message. Queue depth ALONE does not raise an
    issue — a fresh (< STALE_HOURS) mirror or just-arrived message is normal
    traffic; it is AGE, PRIORITY and DLQ state that matter, so the check does
    not flap.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=STALE_HOURS)
    own = f"inbox_{report.get('agent', 'esther')}"
    issues: list[str] = []
    for bus in report.get("buses", []):
        label = bus.get("label", "?")
        if bus.get("inspection_error"):
            issues.append(f"{label}: INSPECTION FAILED — {bus['inspection_error']}")
            continue
        for d in bus.get("dlq", []):
            if d.get("depth", 0) or d.get("processing", 0):
                issues.append(
                    f"{label}: BLOCKED (DLQ) {d['name']} depth={d.get('depth', 0)} "
                    f"processing={d.get('processing', 0)}")
        peeks = bus.get("peeks") or {}
        dated: set[str] = set()
        for qn, peek in peeks.items():
            if not isinstance(peek, dict) or peek.get("error"):
                continue
            msgs = [m for m in (peek.get("messages") or []) if isinstance(m, dict)]
            if not msgs:
                continue
            urgent = [m for m in msgs if isinstance(m.get("priority"), int)
                      and m["priority"] >= URGENT_PRIORITY]
            if urgent:
                issues.append(
                    f"{label}: urgent {qn} — {len(urgent)} msg(s) "
                    f"priority>={URGENT_PRIORITY}")
            stamps = [dt for dt in (_parse_ts(m.get("enqueued_at")) for m in msgs)
                      if dt is not None]
            if not stamps:
                continue
            dated.add(qn)
            stale = [dt for dt in stamps if dt < cutoff]
            if stale:
                issues.append(
                    f"{label}: stale pending {qn} — {len(stale)} msg(s), "
                    f"oldest {min(stale).isoformat()}")
            elif qn == own:
                issues.append(f"{label}: unprocessed {own} depth={len(msgs)}")
        # A non-empty queue we could NOT date (peek window empty / unparseable)
        # is not evidence of 'clean' — surface it rather than stay silent.
        for q in bus.get("nonempty", []):
            if q.get("dlq"):
                continue
            if q.get("depth", 0) and q["name"] not in dated:
                issues.append(f"{label}: undated pending {q['name']} depth={q['depth']}")
    if not report.get("forwarder", {}).get("last_run"):
        issues.append("forwarder: no last_run recorded")
    if report.get("failover", {}).get("failover_active"):
        issues.append("failover: ACTIVE")
    return issues


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    issues_only = "--issues" in argv
    argv = [a for a in argv if not a.startswith("--")]
    agent = argv[0] if argv else "esther"
    report = build_report(agent)
    if issues_only:
        # Runnable no-action check: prints one issue per line, nothing when
        # clean; non-zero exit when a real issue (or a failed inspection) is
        # present, so a dead bus can never read as clean.
        issues = fleet_issues(report)
        if issues:
            print("\n".join(issues))
            return 1
        return 0
    print(json.dumps(report, indent=1))
    return 1 if any(b.get("inspection_error") for b in report.get("buses", [])) else 0


if __name__ == "__main__":
    raise SystemExit(main())
