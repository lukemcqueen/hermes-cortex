#!/usr/bin/env python3
"""
install-cron-cost-tracking.py — Deploy cron cost tracking to Hermes Agent.

Copies cost_store.py into the Hermes agent cron/ directory and patches
scheduler.py / cronjob_tools.py to capture per-run token usage.

Re-run after every ``hermes update`` to re-apply patches (Hermes
replaces its own source directory on update).

Usage:
    python3 install-cron-cost-tracking.py            # apply if missing
    python3 install-cron-cost-tracking.py --force    # re-apply always
    python3 install-cron-cost-tracking.py --status   # check state
"""

import os
import sys
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
HERMES_AGENT = os.path.expanduser("~/.hermes/hermes-agent")
HERMES_CRON = os.path.join(HERMES_AGENT, "cron")
HERMES_TOOLS = os.path.join(HERMES_AGENT, "tools")

# ── File: cost_store.py ────────────────────────────────────
# Deployed to ~/.hermes/hermes-agent/cron/cost_store.py
# Provides: record_run(), get_run_stats(), get_aggregate_stats(), get_latest_run()

# ── Patch: no_agent success path ───────────────────────────
NOAGENT_MARKER = "from cron.cost_store import record_run as _record_run"
NOAGENT_OLD = """        )
        return True, doc, output, None
"""
NOAGENT_NEW = """        )
        # Record zero-cost run for no_agent jobs
        try:
            from cron.cost_store import record_run as _record_run
            _record_run(job_id, {
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
                "api_calls": 0, "estimated_cost_usd": 0.0,
                "model": None, "provider": None,
                "no_agent": True, "status": "ok",
            })
        except Exception:
            print("expected — silently handled", file=sys.stderr)
        return True, doc, output, None
"""

# ── Patch: LLM success path ────────────────────────────────
LLM_MARKER = 'estimated_cost_usd": float(getattr(agent'
LLM_OLD = """            "error": None,
        })
        return True, output, final_response, None
"""
LLM_NEW = """            "error": None,
        })
        # Record token usage and cost for this run
        try:
            from cron.cost_store import record_run as _record_run
            _record_run(job_id, {
                "input_tokens": getattr(agent, "session_input_tokens", 0) or 0,
                "output_tokens": getattr(agent, "session_output_tokens", 0) or 0,
                "cache_read_tokens": getattr(agent, "session_cache_read_tokens", 0) or 0,
                "cache_write_tokens": getattr(agent, "session_cache_write_tokens", 0) or 0,
                "api_calls": getattr(agent, "session_api_calls", 0) or 0,
                "estimated_cost_usd": float(getattr(agent, "session_estimated_cost_usd", 0.0) or 0.0),
                "model": model,
                "provider": str(runtime.get("provider")) if runtime else None,
                "no_agent": False,
                "status": "ok",
            })
        except Exception:
            print("expected — silently handled", file=sys.stderr)
        return True, output, final_response, None
"""

# ── Patch: failure path ────────────────────────────────────
FAIL_MARKER = "_local_agent = locals().get(\"agent\")"
FAIL_INSERT_MARKER = 'return False, output, "", error_msg\n\n    finally:'
FAIL_INSERT = """        # Record partial token usage on failure (agent may be partially initialized)
        try:
            _local_agent = locals().get("agent")
            if _local_agent is not None:
                from cron.cost_store import record_run as _record_run
                _record_run(job_id, {
                    "input_tokens": getattr(_local_agent, "session_input_tokens", 0) or 0,
                    "output_tokens": getattr(_local_agent, "session_output_tokens", 0) or 0,
                    "cache_read_tokens": getattr(_local_agent, "session_cache_read_tokens", 0) or 0,
                    "cache_write_tokens": getattr(_local_agent, "session_cache_write_tokens", 0) or 0,
                    "api_calls": getattr(_local_agent, "session_api_calls", 0) or 0,
                    "estimated_cost_usd": float(getattr(_local_agent, "session_estimated_cost_usd", 0.0) or 0.0),
                    "model": locals().get("model"),
                    "provider": str((locals().get("runtime") or {}).get("provider")) if locals().get("runtime") else None,
                    "no_agent": False,
                    "status": "failure",
                })
        except Exception:
            print("expected — silently handled", file=sys.stderr)
        return False, output, "", error_msg

    finally:"""

# ── Patch: usage_audit cache split (success path) ─────────────
# Extend the JSONL audit line with cache hit/miss tokens so per-run
# cost is computable (the 31x cache lever). DeepSeek/OpenAI-style
# providers report cache_read/cache_write in usage; Hermes exposes
# them as agent.session_cache_*_tokens counters.
AUDIT_CACHE_MARKER = '"prompt_tokens": result.get("prompt_tokens"),'
AUDIT_CACHE_OLD = """            "prompt_tokens": result.get("prompt_tokens"),
            "completion_tokens": result.get("completion_tokens"),
            "total_tokens": result.get("total_tokens"),"""
AUDIT_CACHE_NEW = """            "prompt_tokens": result.get("prompt_tokens"),
            "completion_tokens": result.get("completion_tokens"),
            "total_tokens": result.get("total_tokens"),
            "cache_read_tokens": getattr(agent, "session_cache_read_tokens", 0) or 0,
            "cache_write_tokens": getattr(agent, "session_cache_write_tokens", 0) or 0,"""

# ── Patch: usage_audit cache split (failure path) ─────────────
# NOTE: the failure-path audit write is nested inside `if "_audit_fire_id"
# in locals():` — 16-space indent, unlike the 12-space success path.
AUDIT_FAIL_MARKER = '"response_silent": False,'
AUDIT_FAIL_OLD = """                "total_tokens": None,
                "response_silent": False,"""
AUDIT_FAIL_NEW = """                "total_tokens": None,
                "cache_read_tokens": getattr(agent, "session_cache_read_tokens", 0) or 0,
                "cache_write_tokens": getattr(agent, "session_cache_write_tokens", 0) or 0,
                "response_silent": False,"""

# ── Patch: cronjob_tools.py imports ────────────────────────
TOOLS_IMPORT_MARKER = "_COST_STORE = None"
TOOLS_IMPORT_OLD = """    resume_job,
    update_job,
)

"""
TOOLS_IMPORT_NEW = """    resume_job,
    update_job,
)

# Lazy import for cost store — avoids circular deps at module load
_COST_STORE = None

"""

# ── Patch: cronjob_tools.py _get_cost_store + facade ──────
FACADE_MARKER = "class _CostStoreFacade"
FACADE_OLD = """def _execute_job_now(
    job: Dict[str, Any], extra_prompt: Optional[str] = None
) -> Dict[str, Any]:"""
FACADE_NEW = """def _get_cost_store():
    \"\"\"Lazy-init the cost store helper.\"\"\"
    global _COST_STORE
    if _COST_STORE is None:
        try:
            from cron.cost_store import (
                get_aggregate_stats,
                get_latest_run,
                get_run_stats,
                record_run,
            )
            _COST_STORE = _CostStoreFacade(
                record_run=record_run,
                get_run_stats=get_run_stats,
                get_aggregate_stats=get_aggregate_stats,
                get_latest_run=get_latest_run,
            )
        except Exception:
            print("expected — silently handled", file=sys.stderr)
    return _COST_STORE


class _CostStoreFacade:
    \"\"\"Thin wrapper so _format_job doesn't need to import the store directly.\"\"\"

    def __init__(self, record_run, get_run_stats, get_aggregate_stats, get_latest_run):
        self.record_run = record_run
        self.get_run_stats = get_run_stats
        self.get_aggregate_stats = get_aggregate_stats
        self.get_latest_run = get_latest_run


def _execute_job_now(job: Dict[str, Any]) -> Dict[str, Any]:"""

# ── Patch: _format_job cost enrichment ─────────────────────
FORMAT_MARKER = "last_run_cost"
FORMAT_OLD = """    if external_refs:
        result["context_from"] = external_refs
    return result"""
FORMAT_NEW = """    if external_refs:
        result["context_from"] = external_refs
    # Attach cost data from the cron-costs store
    _cost_store = _get_cost_store()
    if _cost_store:
        latest = _cost_store.get_latest_run(job_id)
        if latest:
            result["last_run_cost"] = {
                "input_tokens": latest.get("input_tokens", 0),
                "output_tokens": latest.get("output_tokens", 0),
                "cache_read_tokens": latest.get("cache_read_tokens", 0),
                "cache_write_tokens": latest.get("cache_write_tokens", 0),
                "api_calls": latest.get("api_calls", 0),
                "estimated_cost_usd": round(float(latest.get("estimated_cost_usd", 0.0)), 6),
                "model": latest.get("model"),
                "provider": latest.get("provider"),
                "no_agent": bool(latest.get("no_agent")),
            }
        agg = _cost_store.get_aggregate_stats(job_id)
        if agg.get("total_runs", 0) > 0:
            result["total_cost"] = {
                "total_runs": agg["total_runs"],
                "total_input_tokens": agg["total_input_tokens"],
                "total_output_tokens": agg["total_output_tokens"],
                "total_cache_read_tokens": agg["total_cache_read_tokens"],
                "total_api_calls": agg["total_api_calls"],
                "total_cost_usd": round(agg["total_cost_usd"], 6),
            }
    return result"""

# ── Patch: costs action in cronjob() dispatch ──────────────
COSTS_MARKER = '"costs"'
COSTS_OLD = """        if normalized == "list":
            jobs = [_format_job(job) for job in list_jobs(include_disabled=include_disabled)]
            return json.dumps({"success": True, "count": len(jobs), "jobs": jobs}, indent=2)

        if not job_id:"""
COSTS_NEW = """        if normalized == "list":
            jobs = [_format_job(job) for job in list_jobs(include_disabled=include_disabled)]
            return json.dumps({"success": True, "count": len(jobs), "jobs": jobs}, indent=2)

        if normalized == "costs":
            \"\"\"Return aggregate cost stats across all or a specific cron job.\"\"\"
            _cost_store = _get_cost_store()
            if not _cost_store:
                return json.dumps(
                    {"success": False, "error": "Cost store not available."}, indent=2
                )
            if job_id:
                stats = _cost_store.get_aggregate_stats(job_id)
                runs = _cost_store.get_run_stats(job_id, limit=20)
            else:
                stats = _cost_store.get_aggregate_stats()
                runs = _cost_store.get_run_stats(limit=20)
            return json.dumps({
                "success": True,
                "job_id": job_id,
                "aggregate": {k: v for k, v in stats.items() if k != "per_job"},
                "total_cost_usd": round(stats.get("total_cost_usd", 0.0), 6),
                "per_model": stats.get("per_model", {}),
                "recent_runs": [
                    {
                        "run_time": r.get("run_time"),
                        "input_tokens": r.get("input_tokens"),
                        "output_tokens": r.get("output_tokens"),
                        "cache_read_tokens": r.get("cache_read_tokens"),
                        "api_calls": r.get("api_calls"),
                        "estimated_cost_usd": round(float(r.get("estimated_cost_usd", 0.0)), 6),
                        "model": r.get("model"),
                        "status": r.get("status"),
                    }
                    for r in runs
                ],
            }, indent=2)

        if not job_id:"""


_PATCHES = [
    ("scheduler.py (no_agent)", NOAGENT_MARKER, NOAGENT_OLD, NOAGENT_NEW),
    ("scheduler.py (LLM success)", LLM_MARKER, LLM_OLD, LLM_NEW),
    ("scheduler.py (failure)", FAIL_MARKER, FAIL_INSERT_MARKER, FAIL_INSERT),
    ("scheduler.py (audit cache success)", AUDIT_CACHE_MARKER, AUDIT_CACHE_OLD, AUDIT_CACHE_NEW),
    ("scheduler.py (audit cache failure)", AUDIT_FAIL_MARKER, AUDIT_FAIL_OLD, AUDIT_FAIL_NEW),
    ("cronjob_tools.py (import)", TOOLS_IMPORT_MARKER, TOOLS_IMPORT_OLD, TOOLS_IMPORT_NEW),
    ("cronjob_tools.py (facade)", FACADE_MARKER, FACADE_OLD, FACADE_NEW),
    ("cronjob_tools.py (format)", FORMAT_MARKER, FORMAT_OLD, FORMAT_NEW),
    ("cronjob_tools.py (costs action)", COSTS_MARKER, COSTS_OLD, COSTS_NEW),
]


def _patch(name, marker, old, new, path, force=False):
    """Apply a patch, replacing old with new. Returns True if changed."""
    with open(path) as f:
        content = f.read()

    if marker in content:
        if not force:
            print(f"  SKIP {name}: already applied (use --force)")
            return False
        # Need to revert first, then re-apply
        if new in content:
            # Already has the new content, skip
            print(f"  SKIP {name}: already applied")
            return False

    if old not in content:
        print(f"  FAIL {name}: marker not found in file")
        return False

    count = content.count(old)
    if count > 1 and old.strip():
        print(f"  FAIL {name}: marker appears {count} times, can't uniquely patch")
        return False

    content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print(f"  OK   {name}")
    return True


def _unpatch(name, marker, old, new, path):
    """Revert a patch. Returns True if changed."""
    with open(path) as f:
        content = f.read()
    if marker not in content:
        print(f"  SKIP {name}: not applied")
        return False
    if new not in content:
        print(f"  SKIP {name}: can't find patch text")
        return False
    content = content.replace(new, old, 1)
    with open(path, 'w') as f:
        f.write(content)
    print(f"  OK   {name} reverted")
    return True


def do_install(force=False):
    print("Step 1: Deploy cost_store.py")
    src = os.path.join(HERE, "cost_store.py")
    dst = os.path.join(HERMES_CRON, "cost_store.py")
    os.makedirs(HERMES_CRON, exist_ok=True)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  OK   {dst}")
    else:
        print(f"  FAIL cost_store.py not found at {src}")
        return False

    print("\nStep 2: Patch cron/scheduler.py")
    sched_path = os.path.join(HERMES_CRON, "scheduler.py")
    if not os.path.exists(sched_path):
        print(f"  FAIL scheduler.py not found at {sched_path}")
        return False

    for name, marker, old, new in _PATCHES[:5]:
        _patch(name, marker, old, new, sched_path, force)

    print("\nStep 3: Patch tools/cronjob_tools.py")
    tools_path = os.path.join(HERMES_TOOLS, "cronjob_tools.py")
    if not os.path.exists(tools_path):
        print(f"  FAIL cronjob_tools.py not found at {tools_path}")
        return False

    for name, marker, old, new in _PATCHES[5:]:
        _patch(name, marker, old, new, tools_path, force)

    print("\n✓ Cron cost tracking deployed.")
    print("  Costs captured on next cron tick.")
    print("  Query: cronjob(action='costs')")
    return True


def do_status():
    print("=== Cron Cost Tracking Status ===")
    # Check cost_store.py
    dst = os.path.join(HERMES_CRON, "cost_store.py")
    if os.path.exists(dst):
        print(f"  OK   cost_store.py: deployed")
    else:
        print(f"  MISS cost_store.py: not deployed")

    # Check patches by looking for the NEW content, not the marker
    sched_path = os.path.join(HERMES_CRON, "scheduler.py")
    tools_path = os.path.join(HERMES_TOOLS, "cronjob_tools.py")

    if os.path.exists(sched_path):
        sched = open(sched_path).read()
        print(f"  {'OK' if 'Record zero-cost run for no_agent' in sched else 'MISS'} scheduler: no_agent hook")
        print(f"  {'OK' if 'Record token usage and cost' in sched else 'MISS'} scheduler: LLM success hook")
        print(f"  {'OK' if 'Record partial token usage on failure' in sched else 'MISS'} scheduler: failure hook")
        _audit_cache_ok = 'session_cache_read_tokens", 0) or 0,' in sched
        print(f"  {'OK' if _audit_cache_ok else 'MISS'} scheduler: audit cache split")

    # rate_version migration (O1-S1) — present in schema after first _get_db() call
    # Note: CRON_DIR is ~/.hermes/cron (cron.jobs), NOT the agent source tree.
    db_path = os.path.expanduser("~/.hermes/cron/cron-costs.db")
    if os.path.exists(db_path):
        import sqlite3
        try:
            con = sqlite3.connect(db_path)
            cols = [r[1] for r in con.execute("PRAGMA table_info(cron_runs)").fetchall()]
            con.close()
            print(f"  {'OK' if 'rate_version' in cols else 'MISS'} cron-costs.db: rate_version column (O1-S1)")
        except Exception as e:
            print(f"  ERR cron-costs.db: rate_version check failed: {e}")

    if os.path.exists(tools_path):
        tools = open(tools_path).read()
        print(f"  {'OK' if '_COST_STORE = None' in tools else 'MISS'} cronjob_tools: cost store import")
        print(f"  {'OK' if 'class _CostStoreFacade' in tools else 'MISS'} cronjob_tools: facade")
        print(f"  {'OK' if 'last_run_cost' in tools else 'MISS'} cronjob_tools: format enrichment")
        costs_action_text = 'normalized == "costs"'
        print(f"  {'OK' if costs_action_text in tools else 'MISS'} cronjob_tools: costs action")


def do_uninstall():
    print("=== Uninstalling Cron Cost Tracking ===")
    sched_path = os.path.join(HERMES_CRON, "scheduler.py")
    tools_path = os.path.join(HERMES_TOOLS, "cronjob_tools.py")

    if os.path.exists(sched_path):
        for name, marker, old, new in _PATCHES[:3]:
            _unpatch(name, marker, old, new, sched_path)

    if os.path.exists(tools_path):
        for name, marker, old, new in _PATCHES[3:]:
            _unpatch(name, marker, old, new, tools_path)

    cost_store = os.path.join(HERMES_CRON, "cost_store.py")
    if os.path.exists(cost_store):
        os.remove(cost_store)
        print(f"  OK   removed cost_store.py")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    force = "--force" in args

    if "--uninstall" in args:
        do_uninstall()
    elif "--status" in args:
        do_status()
    else:
        ok = do_install(force=force)
        sys.exit(0 if ok else 1)
