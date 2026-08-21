#!/usr/bin/env python3
"""
orch-daily-cost-report — One Telegram message: yesterday's fleet spend.

O1-S2 (HC gaps party 2026-08-21). Aggregates:
  - usage_audit.jsonl   (per-cron-run tokens; cache split added O1-S1)
  - cron-costs.db       (per-run estimated cost, when populated)
and produces a compact daily digest: total $, per-category split,
cache-hit %, peak-hour exposure, COVERAGE % (gaps shown, never zeros).

Usage:
    orch-daily-cost-report                  # yesterday's report (text)
    orch-daily-cost-report --days 3         # last 3 days
    orch-daily-cost-report --json           # machine-readable

Exit codes: 0 ok, 1 no data, 2 config error.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
AUDIT = HOME / ".hermes" / "cron" / "usage_audit.jsonl"
COST_DB = HOME / ".hermes" / "cron" / "cron-costs.db"

# DeepSeek v4-flash pricing, USD per 1M tokens (effective 2026-08-16):
# cache-hit input, cache-miss input, output (off-peak). Peak = 2x.
PRICE_HIT = 0.007
PRICE_MISS = 0.22
PRICE_OUT = 0.66
PEAK_MULT = 2.0


def is_peak_hour(dt: datetime) -> bool:
    """DeepSeek peak: 01:00-04:00 and 06:00-10:00 UTC."""
    h = dt.hour
    return (1 <= h < 4) or (6 <= h < 10)


def compute_cost(prompt_tok, comp_tok, cache_read_tok, cache_write_tok, dt) -> float:
    """Estimate USD at current rates. Cache-read counts as hit; the rest misses."""
    hit = cache_read_tok or 0
    miss = max((prompt_tok or 0) - hit, 0)
    mult = PEAK_MULT if is_peak_hour(dt) else 1.0
    return (hit * PRICE_HIT + miss * PRICE_MISS + (comp_tok or 0) * PRICE_OUT) * mult / 1e6


def load_audit(path: Path):
    """Parse usage_audit.jsonl -> list of dicts (tolerant of missing fields)."""
    if not path.exists():
        return None
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def build_report(days: int, audit_path: Path = AUDIT, cost_db: Path = COST_DB):
    now = datetime.utcnow()
    cutoff = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    # sessions table stores started_at as epoch (time.time(), UTC-based).
    # naive-UTC .timestamp() would misread it as LOCAL — compute the epoch
    # from the UTC wall clock directly.
    cutoff_ts = int(cutoff.replace(tzinfo=timezone.utc).timestamp())
    audit_rows = load_audit(audit_path)

    report = {
        "generated_utc": now.isoformat() + "Z",
        "period_days": days,
        "coverage": {},
        "summary": {"runs": 0, "cost_usd": 0.0, "prompt_m": 0.0, "comp_m": 0.0,
                    "cache_hit_pct": None, "peak_runs": 0},
        "by_category": {"cron": {"runs": 0, "cost_usd": 0.0},
                        "session": {"runs": 0, "cost_usd": 0.0, "prompt_m": 0.0, "cache_read_m": 0.0},
                        "subagent": {"runs": 0, "cost_usd": 0.0}},
        "top_jobs": [],
    }

    if audit_rows is None:
        report["coverage"]["usage_audit"] = "MISSING"
    else:
        report["coverage"]["usage_audit"] = "ok"
        job_costs = {}
        total_hit = total_prompt = 0
        for r in audit_rows:
            ts = r.get("ts")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                dt = now
            if dt < cutoff:
                continue
            pt = r.get("prompt_tokens") or 0
            ct = r.get("completion_tokens") or 0
            cr = r.get("cache_read_tokens") or 0
            cw = r.get("cache_write_tokens") or 0
            cost = compute_cost(pt, ct, cr, cw, dt)
            jid = r.get("job_id")
            cat = "cron" if jid else "session"
            if "subagent" in json.dumps(r.get("fire_id", "")) or "deleg" in str(r.get("fire_id", "")):
                cat = "subagent"

            report["summary"]["runs"] += 1
            report["summary"]["cost_usd"] += cost
            report["summary"]["prompt_m"] += pt / 1e6
            report["summary"]["comp_m"] += ct / 1e6
            report["by_category"][cat]["runs"] += 1
            report["by_category"][cat]["cost_usd"] += cost
            total_prompt += pt
            total_hit += cr
            if is_peak_hour(dt):
                report["summary"]["peak_runs"] += 1
            if jid:
                jc = job_costs.setdefault(jid, {"runs": 0, "cost": 0.0})
                jc["runs"] += 1
                jc["cost"] += cost

        if total_prompt > 0:
            report["summary"]["cache_hit_pct"] = round(total_hit / total_prompt * 100, 1)
        report["top_jobs"] = sorted(
            [{"job_id": k[:16], "runs": v["runs"], "cost_usd": round(v["cost"], 4)}
             for k, v in job_costs.items()], key=lambda x: -x["cost_usd"])[:5]

    # cron-costs.db coverage (secondary source)
    if cost_db.exists():
        try:
            con = sqlite3.connect(str(cost_db))
            n = con.execute("SELECT COUNT(*) FROM cron_runs").fetchone()[0]
            con.close()
            report["coverage"]["cron_costs_db"] = f"ok ({n} rows)"
        except Exception as e:
            report["coverage"]["cron_costs_db"] = f"error: {e}"
    else:
        report["coverage"]["cron_costs_db"] = "MISSING"

    # state.db sessions table — interactive (non-cron) per-session tokens + cost.
    # Hermes persists this live per turn for telegram/cli/subagent sources.
    # usage_audit lives at ~/.hermes/cron/usage_audit.jsonl → state.db is parent.parent.
    state_db = audit_path.parent.parent / "state.db"
    if not state_db.exists():
        report["coverage"]["sessions_db"] = "MISSING"
    else:
        try:
            con = sqlite3.connect(str(state_db))
            rows = con.execute("""
                SELECT source, COUNT(*), ROUND(SUM(COALESCE(estimated_cost_usd,0)),2),
                       ROUND(SUM(COALESCE(input_tokens,0))/1e6,1),
                       ROUND(SUM(COALESCE(cache_read_tokens,0))/1e6,1)
                FROM sessions
                WHERE source != 'cron' AND started_at >= ?
                GROUP BY source ORDER BY 3 DESC""", (cutoff_ts,)).fetchall()
            con.close()
            report["coverage"]["sessions_db"] = "ok"
            report["by_category"]["session"]["runs"] = sum(r[1] for r in rows)
            report["by_category"]["session"]["cost_usd"] = round(sum(r[2] for r in rows), 2)
            report["by_category"]["session"]["prompt_m"] = round(sum(r[3] for r in rows), 1)
            report["by_category"]["session"]["cache_read_m"] = round(sum(r[4] for r in rows), 1)
        except Exception as e:
            report["coverage"]["sessions_db"] = f"error: {e}"

    report["summary"]["cost_usd"] = round(report["summary"]["cost_usd"], 2)
    return report


def render_text(r: dict) -> str:
    s = r["summary"]
    cat = r["by_category"]
    cov = r["coverage"]
    lines = [
        f"📊 Fleet Cost — last {r['period_days']}d",
        f"   Total: ${s['cost_usd']:.2f}  ({s['runs']} runs)",
        f"   Tokens → {s['prompt_m']:.0f}M in / {s['comp_m']:.1f}M out",
    ]
    if s["cache_hit_pct"] is not None:
        lines.append(f"   Cache hit: {s['cache_hit_pct']}%  (peak runs: {s['peak_runs']})")
    else:
        lines.append("   Cache hit: n/a (no cache split in audit yet — O1-S1b pending restart)")
    lines.append(f"   Cron ${cat['cron']['cost_usd']:.2f} · Session ${cat['session']['cost_usd']:.2f} · Subagent ${cat['subagent']['cost_usd']:.2f}")
    if cat["session"].get("prompt_m"):
        lines.append(f"   Session detail: {cat['session']['prompt_m']:.0f}M in / {cat['session'].get('cache_read_m', 0):.0f}M cache-read")
    if r["top_jobs"]:
        lines.append("   Top jobs:")
        for j in r["top_jobs"]:
            lines.append(f"     {j['job_id']}: ${j['cost_usd']:.2f} ({j['runs']} runs)")
    gaps = [k for k, v in cov.items() if v == "MISSING"]
    lines.append(f"   Coverage: audit={cov.get('usage_audit')} db={cov.get('cron_costs_db')}"
                 + (f" ⚠️ GAPS: {', '.join(gaps)}" if gaps else ""))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Daily fleet cost digest (O1-S2)")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = build_report(args.days)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(render_text(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
