#!/home/moses/.hermes/hermes-agent/venv/bin/python3
"""
workflow-inspector.py — Inspect agent bus workflows.

Usage:
  python3 workflow-inspector.py                       # List recent workflows
  python3 workflow-inspector.py <workflow-id>          # Drill-down on one workflow
  python3 workflow-inspector.py --all                  # All states (not just active)
  python3 workflow-inspector.py --since 48h            # Lookback window

Silent when no workflows exist. Watchdog pattern.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/hermes-cortex/core"))

# ── DB connection ──────────────────────────────────────────────────

def _load_env():
    """Load CORTEX_BUS_PG_* from ~/hermes-cortex/.env into os.environ."""
    env_path = Path(os.path.expanduser("~/hermes-cortex/.env"))
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip("'\"")
                if k.startswith("CORTEX_BUS_PG"):
                    os.environ.setdefault(k, v)


_load_env()

PG_HOST = os.environ.get("CORTEX_BUS_PG_HOST", "127.0.0.1")
PG_PORT = os.environ.get("CORTEX_BUS_PG_PORT", "15432")
PG_DB = os.environ.get("CORTEX_BUS_PG_DB", "gbrain")
PG_USER = os.environ.get("CORTEX_BUS_PG_USER", "gbrain")
PG_PASS = os.environ.get("CORTEX_BUS_PG_PASS", "gbrain")


def conn():
    import psycopg

    c = psycopg.connect(
        host=PG_HOST,
        port=int(PG_PORT),
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
    )
    return c


# ── Helpers ────────────────────────────────────────────────────────

KST = timedelta(hours=9)


def fmt_ts(ts):
    """Format timestamp to KST short string."""
    if ts is None:
        return "—"
    try:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        local = ts.astimezone(timezone(KST))
        return local.strftime("%m-%d %H:%M")
    except Exception:
        return str(ts)[:16]


def fmt_duration(start, end):
    """Human-readable duration between two timestamps."""
    if start is None:
        return "—"
    end = end or datetime.now(timezone.utc)
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    delta = end - start
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    secs = secs % 60
    if mins < 60:
        return f"{mins}m{secs}s"
    hrs = mins // 60
    mins = mins % 60
    return f"{hrs}h{mins}m"


def state_icon(state):
    icons = {
        "pending": "⏳",
        "running": "🔄",
        "blocked": "🔴",
        "completed": "✅",
        "failed": "❌",
        "timed_out": "⏰",
        "canceled": "🚫",
    }
    return icons.get(state, "❓")


# ── Queries ────────────────────────────────────────────────────────


def list_workflows(since_hours=24, all_states=False):
    """Return list of workflow summaries."""
    with conn() as c:
        states_filter = "" if all_states else "AND w.state IN ('pending','running','blocked')"
        sql = f"""
            SELECT w.id::text, w.name, w.state, w.created_at, w.started_at,
                   w.completed_at, w.owner_agent
            FROM bus.agent_workflows w
            WHERE w.created_at > NOW() - INTERVAL '{since_hours} hours'
            {states_filter}
            ORDER BY w.created_at DESC
            LIMIT 20
        """
        return c.execute(sql).fetchall()


def get_workflow(wf_id):
    """Get full workflow detail."""
    with conn() as c:
        wf = c.execute(
            """
            SELECT id::text, name, state, version, priority, payload, result, error,
                   created_at, started_at, completed_at, deadline_at, owner_agent,
                   correlation_id
            FROM bus.agent_workflows
            WHERE id::text = %s
            """,
            (wf_id,),
        ).fetchone()
        if not wf:
            # Try partial match
            wf = c.execute(
                """
                SELECT id::text, name, state, version, priority, payload, result, error,
                       created_at, started_at, completed_at, deadline_at, owner_agent,
                       correlation_id
                FROM bus.agent_workflows
                WHERE id::text LIKE %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (wf_id + "%",),
            ).fetchone()

        if not wf:
            return None

        steps = c.execute(
            """
            SELECT step_name, step_order, state, assigned_to, result, error,
                   started_at, completed_at, timeout_seconds, retry_count, max_retries
            FROM bus.agent_workflow_steps
            WHERE workflow_id = %s::uuid
            ORDER BY step_order
            """,
            (wf[0],),
        ).fetchall()
        return wf, steps


# ── Formatters ─────────────────────────────────────────────────────


def format_list(rows):
    if not rows:
        return ""
    lines = ["Recent workflows:"]
    for r in rows:
        wf_id, name, state, created, started, completed, owner = r
        icon = state_icon(state)
        dur = fmt_duration(started or created, completed)
        lines.append(
            f"  {icon} {wf_id[:8]}  {name[:28]:28s}  {state:10s}  {fmt_ts(created)}  "
            f"{dur:8s}  {owner or '—'}"
        )
    return "\n".join(lines)


def format_detail(wf, steps):
    cols = [
        ("ID", wf[0][:8]),
        ("Name", wf[1]),
        ("State", f"{state_icon(wf[2])} {wf[2]}"),
        ("Version", wf[3] or "—"),
        ("Priority", str(wf[4] or "—")),
        ("Owner", wf[12] or "—"),
        ("Correlation", wf[13] or "—"),
        ("Created", fmt_ts(wf[8])),
        ("Started", fmt_ts(wf[9])),
        ("Completed", fmt_ts(wf[10])),
        ("Deadline", fmt_ts(wf[11])),
        ("Duration", fmt_duration(wf[9] or wf[8], wf[10])),
    ]
    lines = [f"Workflow: {wf[1]}"]
    lines.append("─" * 48)
    for label, val in cols:
        lines.append(f"  {label:12s}  {val}")

    if wf[6]:  # result
        try:
            result = json.dumps(wf[6], indent=2) if isinstance(wf[6], dict) else str(wf[6])
            lines.append(f"\n  Result:     {result[:500]}")
        except Exception:
            pass
    if wf[7]:  # error
        lines.append(f"\n  Error:      {wf[7][:500]}")

    if steps:
        lines.append(f"\n  Steps ({len(steps)}):")
        lines.append("  " + "─" * 44)
        for s in steps:
            sn, order, state, assigned, result, err, started, completed, timeout, retry, maxretry = s
            icon = state_icon(state)
            dur = fmt_duration(started, completed)
            retry_str = f" (retry {retry}/{maxretry})" if retry and retry > 0 else ""
            line = f"  {icon}  {sn[:24]:24s}  {state:10s}  {assigned or '—':10s}  {dur:8s}{retry_str}"
            lines.append(line)
            if err:
                lines.append(f"       ⚠ {err[:200]}")
        lines.append("  " + "─" * 44)

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--h")]
    all_states = "--all" in sys.argv
    since = 24
    for a in sys.argv:
        if a.startswith("--since="):
            val = a.split("=", 1)[1]
            if val.endswith("h"):
                since = int(val[:-1])
            elif val.endswith("d"):
                since = int(val[:-1]) * 24
            else:
                since = int(val)

    wf_id = None
    for a in args:
        if not a.startswith("--"):
            wf_id = a
            break

    try:
        if wf_id:
            detail = get_workflow(wf_id)
            if detail is None:
                print(f"Workflow not found: {wf_id}")
                sys.exit(1)
            wf, steps = detail
            print(format_detail(wf, steps))
        else:
            rows = list_workflows(since_hours=since, all_states=all_states)
            output = format_list(rows)
            if output:
                print(output)
            # silent if no rows (watchdog pattern)
    except Exception as e:
        print(f"[workflow-inspector] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
