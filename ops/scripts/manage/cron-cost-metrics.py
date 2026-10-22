#!/usr/bin/env python3
"""cron-cost-metrics.py — per-cron token/spend series for the metrics sink.

Story c579ef95 [cost/3]: the sink (VictoriaMetrics behind the :14005 proxy) must
carry cost, not only node metrics. Two truths are read, neither is invented:

  tokens  ~/.hermes/cron/usage_audit.jsonl   one JSON object per cron fire
  spend   ~/.hermes/state.db -> sessions     estimated_cost_usd, source='cron'

NO price table is stored here. Stored prices rot on every provider hike — that is
exactly why the cron-costs.db / cost_store.py stack was removed on 2026-10-06.
Hermes writes estimated_cost_usd live per session at current prices, so that
column IS the spend truth and this tool never re-derives it.

Exit codes:
  0  series emitted (an unreadable spend source is emitted as unavailable, not as 0)
  2  nothing readable at all — the caller must treat this as "no data", never as $0
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_AUDIT = Path.home() / ".hermes" / "cron" / "usage_audit.jsonl"
DEFAULT_STATE_DB = Path.home() / ".hermes" / "state.db"


def read_tokens(path: Path):
    """Return (tokens_by_job, fires_by_job), or (None, None) when unreadable."""
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return None, None
    tokens: dict[str, float] = defaultdict(float)
    fires: dict[str, int] = defaultdict(int)
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
        fires[job] += 1
        try:
            tokens[job] += float(row.get("total_tokens") or 0)
        except (TypeError, ValueError):
            pass
    return tokens, fires


def read_costs(db_path: Path):
    """Return {job_id: usd} over all cron sessions, or None when unreadable."""
    try:
        con = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        rows = con.execute(
            "SELECT id, estimated_cost_usd FROM sessions WHERE source = 'cron'"
        ).fetchall()
    except sqlite3.Error:
        return None
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
    return per_job


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
    p.add_argument("--prometheus", action="store_true", required=True,
                   help="emit Prometheus text exposition (the only supported mode)")
    p.add_argument("--agent", default=os.environ.get("AGENT_NAME", ""),
                   help="agent label (default: $AGENT_NAME)")
    p.add_argument("--audit", default=str(DEFAULT_AUDIT), help="usage_audit.jsonl path")
    p.add_argument("--state-db", default=str(DEFAULT_STATE_DB), help="state.db path")
    args = p.parse_args()

    if not args.agent:
        print("[cron-cost-metrics] AGENT_NAME not set — refusing to label metrics as unknown",
              file=sys.stderr)
        return 2

    tokens, fires = read_tokens(Path(args.audit))
    costs = read_costs(Path(args.state_db))
    if tokens is None and costs is None:
        print(f"[cron-cost-metrics] no readable source: {args.audit} and {args.state_db}",
              file=sys.stderr)
        return 2
    print(emit(args.agent, tokens or {}, fires or {}, costs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
