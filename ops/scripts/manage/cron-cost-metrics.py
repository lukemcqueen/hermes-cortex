#!/usr/bin/env python3
"""cron-cost-metrics.py — per-cron token/spend series + the host cost summary.

Story c579ef95 [cost/3]: the sink (VictoriaMetrics behind the :14005 proxy) must
carry cost, not only node metrics. Two truths are read, neither is invented:

  tokens  ~/.hermes/cron/usage_audit.jsonl   one JSON object per cron fire
  spend   ~/.hermes/state.db -> sessions     estimated_cost_usd, source='cron'

[cost/4] added the second mode, `--json-summary`: ONE compact JSON object a
worker host can return over the bus, because each host can read only its OWN
cron audit log and the orchestrator cannot read it for them. It carries a
window (`--since`), per-day fire/token totals, per-job totals, this host's own
identity, and one bounded probe of the local Langfuse daily metrics endpoint —
which reports absence as an ANSWER ("nothing listening here"), never as a
missing number.

NO price table is stored here. Stored prices rot on every provider hike — that is
exactly why the cron-costs.db / cost_store.py stack was removed on 2026-10-06.
Hermes writes estimated_cost_usd live per session at current prices, so that
column IS the spend truth and this tool never re-derives it.

Exit codes:
  0  series/summary emitted (an unreadable spend source is emitted as unavailable, not as 0)
  2  nothing readable at all, or no host identity — the caller must treat this as
     "no data", never as $0
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULT_AUDIT = Path.home() / ".hermes" / "cron" / "usage_audit.jsonl"
DEFAULT_STATE_DB = Path.home() / ".hermes" / "state.db"
DEFAULT_LANGFUSE_URL = "http://127.0.0.1:3000"
LANGFUSE_LIMIT = 7
LANGFUSE_TIMEOUT_S = 5
PER_JOB_CAP = 15

# Host-derived identity, in the same order and from the same files the bus
# command handler uses (ops/scripts/agent/commands.py:_agent_name). An EXEC
# passes no --agent, so without this the aggregate cannot be attributed — and a
# label of "unknown" is worse than a refusal (SOUL Principle 3).
IDENTITY_FILES = (
    Path.home() / ".hermes-cortex" / "agent.env",
    Path.home() / "hermes-cortex" / ".env",
)


def resolve_agent(explicit: str | None) -> str:
    """Return the host's agent label, or "" when it cannot be resolved.

    `--agent ""` is a caller error (refused), `--agent` absent means "ask the
    host" — the two are different requests and are kept different here.
    """
    if explicit is not None:
        return explicit.strip()
    env = (os.environ.get("AGENT_NAME") or "").strip()
    if env:
        return env
    for path in IDENTITY_FILES:
        try:
            if not path.is_file():
                continue
            for line in path.read_text().splitlines():
                if line.startswith("AGENT_NAME="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        return val
        except OSError:
            continue
    return ""


def _parse_ts(value) -> date | None:
    """The row's own UTC date, or None when the value cannot be placed in time."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def scan_audit(path: Path, since: date | None = None) -> dict | None:
    """Aggregate the audit log. Returns None when the file cannot be read.

    With no window nothing is dropped for a missing timestamp: there is nothing
    to place it in, so `ts` is simply not a requirement. With a window, a row
    that cannot be dated is counted in `skipped_rows` and never lands in a day
    — an unplaceable row is declared, not silently averaged in.
    """
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return None
    tokens: dict[str, float] = defaultdict(float)
    fires: dict[str, int] = defaultdict(int)
    per_day: dict[str, dict] = {}
    skipped = 0
    rows = 0
    first_ts = last_ts = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a torn last line from a live writer is normal, not fatal
        if not isinstance(row, dict):
            continue
        job = row.get("job_id")
        if not isinstance(job, str) or not job:
            continue
        rows += 1
        day = _parse_ts(row.get("ts"))
        if day is None:
            if since is not None:
                skipped += 1
                continue
        else:
            raw = row.get("ts")
            if isinstance(raw, str) and raw:
                first_ts = raw if first_ts is None else min(first_ts, raw)
                last_ts = raw if last_ts is None else max(last_ts, raw)
            if since is not None and day < since:
                continue
        try:
            amount = float(row.get("total_tokens") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        fires[job] += 1
        tokens[job] += amount
        if day is not None:
            bucket = per_day.setdefault(day.isoformat(), {"fires": 0, "tokens": 0.0})
            bucket["fires"] += 1
            bucket["tokens"] += amount
    return {
        "rows": rows,
        "skipped_rows": skipped,
        "tokens": dict(tokens),
        "fires": dict(fires),
        "per_day": per_day,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def read_tokens(path: Path):
    """Return (tokens_by_job, fires_by_job), or (None, None) when unreadable."""
    scanned = scan_audit(path, since=None)
    if scanned is None:
        return None, None
    return scanned["tokens"], scanned["fires"]


def read_costs(db_path: Path) -> tuple[dict | None, str]:
    """Return ({job_id: usd}, reason) — reason non-empty when unreadable."""
    try:
        con = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as e:
        return None, f"cannot open {db_path}: {type(e).__name__}"
    try:
        rows = con.execute(
            "SELECT id, estimated_cost_usd FROM sessions WHERE source = 'cron'"
        ).fetchall()
    except sqlite3.Error as e:
        return None, f"cannot read sessions in {db_path}: {type(e).__name__}"
    finally:
        con.close()
    per_job: dict[str, float] = defaultdict(float)
    for sid, cost in rows:
        if not sid:
            continue
        # Cron session ids are `cron_<jobid>_<ts>` (state.db.sessions.id — the
        # column is `id`, verified 2026-10-22 against the live schema; there is
        # no `session_id` column, which is what the first version of this
        # generator assumed and the evidence transcript caught).
        parts = str(sid).split("_")
        job = parts[1] if len(parts) >= 3 else str(sid)
        try:
            per_job[job] += float(cost or 0)
        except (TypeError, ValueError):
            pass
    return per_job, ""


def _langfuse_credentials() -> tuple[str, str]:
    """(public, secret) from the environment, else from ~/.hermes/.env.

    Never printed, never logged: the pair is only ever turned into an
    Authorization header in-process.
    """
    pub = (os.environ.get("HERMES_LANGFUSE_PUBLIC_KEY") or "").strip()
    sec = (os.environ.get("HERMES_LANGFUSE_SECRET_KEY") or "").strip()
    if pub and sec:
        return pub, sec
    dotenv = Path.home() / ".hermes" / ".env"
    try:
        for line in dotenv.read_text(errors="replace").splitlines():
            line = line.strip()
            if line.startswith("HERMES_LANGFUSE_PUBLIC_KEY=") and not pub:
                pub = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("HERMES_LANGFUSE_SECRET_KEY=") and not sec:
                sec = line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return pub, sec


def probe_langfuse(url: str) -> dict:
    """One bounded read of the local Langfuse daily metrics endpoint.

    Three honest outcomes, and no fourth:
      present True   — an HTTP response came back (days included only on 200)
      present False  — nothing is listening there: this host has no Langfuse
      present True + error — something answered but the read failed
    A failure never becomes a fabricated 0 cost.
    """
    base = (url or "").strip().rstrip("/")
    if not base:
        return {"checked": True, "present": False, "reason": "no langfuse url configured"}
    req = urllib.request.Request(f"{base}/api/public/metrics/daily?limit={LANGFUSE_LIMIT}")
    pub, sec = _langfuse_credentials()
    if pub and sec:
        token = base64.b64encode(f"{pub}:{sec}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=LANGFUSE_TIMEOUT_S) as resp:
            status = getattr(resp, "status", 200)
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"checked": True, "present": True,
                "error": f"HTTP {e.code} from {base}"}
    except (urllib.error.URLError, OSError) as e:
        return {"checked": True, "present": False,
                "reason": f"nothing listening at {base} ({type(e).__name__})"}
    except ValueError as e:
        return {"checked": True, "present": True,
                "error": f"unparseable response from {base}: {type(e).__name__}"}
    days = []
    for row in (payload.get("data") or []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        days.append({
            "date": row["date"],
            "traces": row.get("countTraces"),
            "cost_usd": row.get("totalCost"),
        })
    return {"checked": True, "present": True, "status": status, "days": days}


def build_summary(agent: str, audit_path: Path, db_path: Path, since: date | None,
                  langfuse_url: str) -> dict:
    scanned = scan_audit(audit_path, since=since) or {
        "rows": 0, "skipped_rows": 0, "tokens": {}, "fires": {},
        "per_day": {}, "first_ts": None, "last_ts": None,
    }
    costs, cost_reason = read_costs(db_path)
    per_job = [
        {"job_id": job, "fires": scanned["fires"].get(job, 0), "tokens": scanned["tokens"][job]}
        for job in scanned["tokens"]
    ]
    # Deterministic: tokens desc, job_id asc as the tie-break, so two runs on
    # the same log cannot disagree about the order.
    per_job.sort(key=lambda r: (-r["tokens"], r["job_id"]))
    omitted = max(0, len(per_job) - PER_JOB_CAP)
    per_day = [
        {"date": day, "fires": bucket["fires"], "tokens": bucket["tokens"]}
        for day, bucket in sorted(scanned["per_day"].items())
    ]
    if costs is None:
        spend = {"available": False, "reason": cost_reason or "unreadable"}
    else:
        spend = {
            "available": True,
            "lifetime_usd": round(sum(costs.values()), 6),
            "per_job": {k: round(v, 6) for k, v in sorted(costs.items())},
        }
    return {
        "agent": agent,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "audit": {
            "path": str(audit_path),
            "rows": scanned["rows"],
            "skipped_rows": scanned["skipped_rows"],
            "first_ts": scanned["first_ts"],
            "last_ts": scanned["last_ts"],
        },
        "window": {"since": since.isoformat() if since else None},
        "per_day": per_day,
        "per_job": per_job[:PER_JOB_CAP],
        "per_job_omitted": omitted,
        "spend": spend,
        "langfuse": probe_langfuse(langfuse_url),
    }


def emit(agent: str, tokens, fires, costs) -> str:
    tag = f'agent="{agent}"'
    out: list[str] = []
    if tokens:
        out.append("# HELP hermes_cron_tokens_total Cron tokens consumed per job (lifetime, audit log)")
        out.append("# TYPE hermes_cron_tokens_total counter")
        for job in sorted(tokens):
            out.append(f'hermes_cron_tokens_total{{{tag},job_id="{job}"}} {tokens[job]:g}')
        out.append("# HELP hermes_cron_fires_total Cron fires per job")
        out.append("# TYPE hermes_cron_fires_total counter")
        for job in sorted(fires):
            out.append(f'hermes_cron_fires_total{{{tag},job_id="{job}"}} {fires[job]}')
    if costs is None:
        # An absent series is visible; a false 0 is not.
        out.append("# HELP hermes_cron_cost_available 1 = spend read from state.db, 0 = unavailable")
        out.append("# TYPE hermes_cron_cost_available gauge")
        out.append(f'hermes_cron_cost_available{{{tag}}} 0')
        print(
            "[cron-cost-metrics] spend source unavailable (state.db unreadable) — "
            "cost series omitted this push; spend is NOT zero",
            file=sys.stderr,
        )
    else:
        out.append("# HELP hermes_cron_cost_usd Estimated cron spend per job (lifetime, state.db)")
        out.append("# TYPE hermes_cron_cost_usd gauge")
        total = 0.0
        for job in sorted(costs):
            out.append(f'hermes_cron_cost_usd{{{tag},job_id="{job}"}} {costs[job]:.6f}')
            total += costs[job]
        out.append("# HELP hermes_cron_cost_available 1 = spend read from state.db, 0 = unavailable")
        out.append("# TYPE hermes_cron_cost_available gauge")
        out.append(f'hermes_cron_cost_available{{{tag}}} 1')
        out.append("# HELP hermes_cron_cost_usd_total Estimated cron spend, all jobs (lifetime)")
        out.append("# TYPE hermes_cron_cost_usd_total gauge")
        out.append(f'hermes_cron_cost_usd_total{{{tag}}} {total:.6f}')
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prometheus", action="store_true",
                      help="emit Prometheus text exposition (the metrics-push payload)")
    mode.add_argument("--json-summary", action="store_true",
                      help="emit one compact JSON object for a bus EXEC_RESULT")
    p.add_argument("--agent", default=None,
                   help="agent label (default: $AGENT_NAME, then the host's agent.env)")
    p.add_argument("--audit", default=str(DEFAULT_AUDIT), help="usage_audit.jsonl path")
    p.add_argument("--state-db", default=str(DEFAULT_STATE_DB), help="state.db path")
    p.add_argument("--since", default=None,
                   help="YYYY-MM-DD; --json-summary only — the window start (UTC)")
    p.add_argument("--langfuse-url", default=os.environ.get("HERMES_LANGFUSE_BASE_URL")
                   or DEFAULT_LANGFUSE_URL,
                   help="local Langfuse base URL probed once in --json-summary mode")
    args = p.parse_args()

    # Deliberately NOT applied in --prometheus mode: agent-push-metrics.sh runs
    # this every 5 minutes on every host and never passes --since, so the pushed
    # payload's meaning must not change because a window option exists.
    since = None
    if args.since:
        try:
            since = date.fromisoformat(args.since.strip())
        except ValueError:
            p.error(f"--since must be YYYY-MM-DD, got {args.since!r}")

    agent = resolve_agent(args.agent)
    if not agent:
        print("[cron-cost-metrics] AGENT_NAME not set and no host agent.env — "
              "refusing to label metrics as unknown", file=sys.stderr)
        return 2

    if args.json_summary:
        print(json.dumps(build_summary(agent, Path(args.audit), Path(args.state_db),
                                       since, args.langfuse_url)))
        return 0

    audit_path = Path(args.audit)
    tokens, fires = read_tokens(audit_path)
    costs, _reason = read_costs(Path(args.state_db))
    if tokens is None and costs is None:
        print(f"[cron-cost-metrics] no readable source: {args.audit} and {args.state_db}",
              file=sys.stderr)
        return 2
    print(emit(agent, tokens or {}, fires or {}, costs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
