#!/usr/bin/env python3
"""cron_manifest.py — Canonical cron manifest reader + drift engine.

Single source of truth for fleet crons: `ops/install/cron-manifest.yaml`.
The installers (install-crons.sh / install-orch-crons.sh / install-dream-crons.sh)
read this module to create/update crons; the doctor uses it to verify live
jobs.json against the manifest across ALL fields (not just name existence).

Scope model:
    universal     — every agent installs and verifies
    orchestrator  — only moses/esther (host-derived, NEVER env)
    opt-in        — only when opt_in_marker file exists (e.g. dream layer)

Per-host values in the manifest use placeholders:
    {{HOME}}          → $HOME (workdir)
    {{HOME_CHANNEL}}  → telegram home channel id (deliver)

Schedule = BASE schedule. The minute is rewritten per-host at install time
(cksum(hostname:cron-name) % 60, Luke directive 2026-08-07) so fleet hosts
don't all fire the same LLM cron at :00. no_agent crons keep exact minutes.

Exit codes (CLI):
    0 = clean (no drift / check passed)
    1 = drift found (--check)
    2 = error
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# ── Paths ──────────────────────────────────────────────────────────────
CORTEX_REPO = Path(os.environ.get("CORTEX_REPO", os.path.expanduser("~/hermes-cortex")))
MANIFEST_PATH = CORTEX_REPO / "ops" / "install" / "cron-manifest.yaml"
JOBS_FILE = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "cron" / "jobs.json"

# Scopes
SCOPE_UNIVERSAL = "universal"
SCOPE_ORCHESTRATOR = "orchestrator"
SCOPE_OPT_IN = "opt-in"


# ── Host identity (orchestrator = hostname + home dir, never env) ─────
def _hostname() -> str:
    try:
        return subprocess.run(["hostname", "-s"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return os.uname().nodename.split(".")[0]


def _is_orchestrator() -> bool:
    """Orchestrator status is host-derived: hostname moses|esther AND matching home dir."""
    host = _hostname()
    if host not in ("moses", "esther"):
        return False
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    try:
        import pwd
        home = pwd.getpwnam(user).pw_dir
    except Exception:
        home = os.path.expanduser("~")
    return home == f"/home/{host}"


def _stagger_minute(name: str) -> str:
    """Deterministic per-host minute: cksum(hostname:cron-name) % 60."""
    host = _hostname()
    try:
        r = subprocess.run(["cksum"], input=f"{host}:{name}".encode(), capture_output=True, timeout=5)
        digest = r.stdout.split()[0]
        return str(int(digest) % 60)
    except Exception:
        return "0"


def _expand_placeholders(value: str) -> str:
    """Expand {{HOME}} / {{HOME_CHANNEL}} to live per-host values."""
    if not value:
        return value
    value = value.replace("{{HOME}}", os.path.expanduser("~"))
    home_channel = os.environ.get("TELEGRAM_HOME_CHANNEL", "")
    if not home_channel:
        # The doctor / cron contexts don't always inherit ~/.hermes/.env —
        # source it like the installers do (best-effort, never fatal).
        for env_candidate in (Path(os.path.expanduser("~/.hermes/.env")),
                              Path(os.path.expanduser("~/hermes-cortex/.env"))):
            try:
                if not env_candidate.exists():
                    continue
                for raw in env_candidate.read_text().splitlines():
                    line = raw.strip()
                    if line.startswith("TELEGRAM_HOME_CHANNEL="):
                        home_channel = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
                if home_channel:
                    break
            except Exception:
                continue
    value = value.replace("{{HOME_CHANNEL}}", home_channel)
    return value


# ── Manifest loading ───────────────────────────────────────────────────
def load_manifest(path: Optional[Path] = None) -> list[dict]:
    """Load cron definitions from the manifest. Returns [] on error."""
    p = path or MANIFEST_PATH
    if not p.exists():
        return []
    try:
        import yaml
        doc = yaml.safe_load(p.read_text())
    except Exception:
        return []
    if not isinstance(doc, dict) or not isinstance(doc.get("crons"), list):
        return []
    return doc["crons"]


def is_in_scope(cron: dict, is_orch: Optional[bool] = None) -> bool:
    """True when this cron applies to the current host."""
    scope = cron.get("scope", SCOPE_UNIVERSAL)
    if scope == SCOPE_UNIVERSAL:
        return True
    if scope == SCOPE_ORCHESTRATOR:
        return _is_orchestrator() if is_orch is None else is_orch
    if scope == SCOPE_OPT_IN:
        marker = cron.get("opt_in_marker", "")
        if not marker:
            return False
        marker_path = Path(os.path.expanduser("~/.hermes-cortex")) / marker
        return marker_path.exists()
    return False


def expected_schedule(cron: dict) -> str:
    """Base schedule with the per-host stagger minute applied for LLM crons."""
    sched = cron.get("schedule", "")
    if cron.get("no_agent"):
        return sched
    # only stagger standard 5-field cron expressions (not 'every 10m' / ISO)
    if re.match(r"^[0-9*/,]+(\s+[^ ]+){4}$", sched):
        parts = sched.split()
        parts[0] = _stagger_minute(cron.get("name", ""))
        return " ".join(parts)
    return sched


def desired_state(cron: dict) -> dict:
    """The live jobs.json fields this cron SHOULD have on this host."""
    return {
        "schedule": expected_schedule(cron),
        "script": cron.get("script", "") or "",
        "prompt": cron.get("prompt", "") or "",
        "skill": cron.get("skill", "") or "",
        "deliver": _expand_placeholders(cron.get("deliver", "origin")),
        "workdir": _expand_placeholders(cron.get("workdir", "")),
        "no_agent": bool(cron.get("no_agent", False)),
        "model": cron.get("model", "") or "",
        "provider": cron.get("provider", "") or "",
    }


def load_live_jobs() -> dict[str, dict]:
    """Load live jobs.json keyed by name."""
    if not JOBS_FILE.exists():
        return {}
    try:
        data = json.loads(JOBS_FILE.read_text())
    except Exception:
        return {}
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    return {j.get("name"): j for j in jobs if isinstance(j, dict) and j.get("name")}


def live_schedule_expr(live: dict) -> str:
    """Normalize live schedule to its display form ('*/10 * * * *' or 'every 10m')."""
    sched = live.get("schedule")
    if isinstance(sched, dict):
        if sched.get("kind") == "interval":
            return sched.get("display", "")
        return sched.get("expr", "") or sched.get("display", "")
    return str(sched or "")


def diff_cron(live: dict, desired: dict) -> list[str]:
    """Return list of field-drift descriptions between live and desired."""
    drift = []
    live_expr = live_schedule_expr(live)
    if live_expr != desired["schedule"]:
        drift.append(f"schedule {live_expr!r} → {desired['schedule']!r}")
    for field in ("script", "prompt", "skill", "deliver", "workdir", "model", "provider"):
        lv = live.get(field) or ""
        dv = desired[field]
        if lv != dv:
            if field == "prompt":
                drift.append(f"prompt differs ({len(lv)} → {len(dv)} chars)")
            else:
                drift.append(f"{field} {lv!r} → {dv!r}")
    # no_agent
    if bool(live.get("no_agent")) != desired["no_agent"]:
        drift.append(f"no_agent {bool(live.get('no_agent'))} → {desired['no_agent']}")
    return drift


def check_drift(verbose: bool = False) -> tuple[list[dict], list[dict], list[str]]:
    """Compare manifest vs live. Returns (drifted, missing, errors)."""
    crons = load_manifest()
    live = load_live_jobs()
    drifted: list[dict] = []
    missing: list[dict] = []
    errors: list[str] = []

    manifest_names = set()
    for cron in crons:
        name = cron.get("name", "")
        if not name:
            continue
        if not is_in_scope(cron):
            continue
        manifest_names.add(name)
        if name not in live:
            missing.append(cron)
            continue
        desired = desired_state(cron)
        diffs = diff_cron(live[name], desired)
        if diffs:
            drifted.append({"name": name, "diffs": diffs, "desired": desired})

    # orphans: live crons with a managed prefix that the manifest doesn't declare
    expected_prefixes = ("agent-", "orch-")
    orphan_names = [
        n for n, j in live.items()
        if any(n.startswith(p) for p in expected_prefixes) and n not in manifest_names
    ]
    return drifted, missing, orphan_names


# ── Repair engine ─────────────────────────────────────────────────────
def _hermes_cmd() -> str:
    """Locate the hermes CLI."""
    import shutil
    return shutil.which("hermes") or "hermes"


def repair_cron(cron: dict, dry_run: bool = False) -> tuple[str, str]:
    """Create or update a live cron to match the manifest. Returns (action, detail)."""
    name = cron.get("name", "")
    live = load_live_jobs()
    desired = desired_state(cron)
    hermes = _hermes_cmd()

    # Base CLI args shared by create and edit
    def _field_args() -> list[str]:
        args = []
        if desired["script"]:
            args += ["--script", desired["script"]]
        if desired["prompt"]:
            args += ["--prompt", desired["prompt"]]
        if desired["skill"]:
            args += ["--skill", desired["skill"]]
        if desired["deliver"]:
            args += ["--deliver", desired["deliver"]]
        if desired["workdir"]:
            args += ["--workdir", desired["workdir"]]
        if desired["no_agent"]:
            args += ["--no-agent"]
        else:
            args += ["--agent"]
        return args

    if name in live:
        # Edit existing — only pass fields that changed
        job_id = live[name].get("id", "")
        if not job_id:
            return ("error", f"{name}: no job_id in live state")
        diffs = diff_cron(live[name], desired)
        if not diffs:
            return ("skip", f"{name}: no drift")
        # Only pass fields that actually changed; hermes edit is per-field idempotent
        edit_args = [hermes, "cron", "edit", job_id, "--schedule", desired["schedule"]]
        for field, flag in (("script", "--script"), ("prompt", "--prompt"), ("skill", "--skill"),
                            ("deliver", "--deliver"), ("workdir", "--workdir")):
            if (live[name].get(field) or "") != desired[field]:
                # Pass the field even when desired is empty — hermes edit treats
                # an empty string as "clear the field" (e.g. stale prompt on a
                # no_agent script cron). Previously the `and desired[field]`
                # guard skipped empty targets, so repair logged "UPDATED" but
                # never cleared the drift.
                edit_args += [flag, desired[field]]
        if bool(live[name].get("no_agent")) != desired["no_agent"]:
            edit_args += ["--no-agent"] if desired["no_agent"] else ["--agent"]
        if dry_run:
            return ("would-edit", f"{name}: {', '.join(diffs)}")
        try:
            r = subprocess.run(edit_args, capture_output=True, text=True, timeout=60)
        except Exception as e:
            return ("error", f"{name}: {e}")
        if r.returncode != 0:
            return ("error", f"{name}: {r.stderr.strip()[:120]}")
        _pin_model(name, desired["model"], desired["provider"])
        return ("updated", f"{name}: {', '.join(diffs)}")
    else:
        # Create
        create_args = [hermes, "cron", "create", "--name", name, "--schedule", desired["schedule"]]
        create_args += _field_args()
        if dry_run:
            return ("would-create", name)
        try:
            r = subprocess.run(create_args, capture_output=True, text=True, timeout=60)
        except Exception as e:
            return ("error", f"{name}: {e}")
        if r.returncode != 0:
            return ("error", f"{name}: {r.stderr.strip()[:120]}")
        _pin_model(name, desired["model"], desired["provider"])
        return ("created", name)


def _pin_model(name: str, model: str, provider: str) -> None:
    """Set model/provider on a live cron via jobs.json patch (CLI has no --model)."""
    if not model and not provider:
        return
    if not JOBS_FILE.exists():
        return
    try:
        data = json.loads(JOBS_FILE.read_text())
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        for job in jobs:
            if isinstance(job, dict) and job.get("name") == name:
                if model:
                    job["model"] = model
                if provider:
                    job["provider"] = provider
                break
        else:
            return
        if isinstance(data, dict):
            data["jobs"] = jobs
            JOBS_FILE.write_text(json.dumps(data, indent=2, default=str))
        else:
            JOBS_FILE.write_text(json.dumps(jobs, indent=2, default=str))
    except Exception:
        pass


def repair_all(scope_filter: Optional[str] = None, dry_run: bool = False) -> list[dict]:
    """Repair all in-scope crons. Returns list of {name, action, detail}."""
    results = []
    for cron in load_manifest():
        if not is_in_scope(cron):
            continue
        if scope_filter and cron.get("scope") != scope_filter:
            continue
        action, detail = repair_cron(cron, dry_run=dry_run)
        results.append({"name": cron.get("name"), "action": action, "detail": detail})
    return results


# ── CLI ────────────────────────────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Canonical cron manifest reader/drift checker")
    ap.add_argument("--check", action="store_true", help="exit 1 if any drift/missing")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--list-in-scope", action="store_true", help="list crons in scope for this host")
    ap.add_argument("--repair", action="store_true", help="create missing + edit drifted crons")
    ap.add_argument("--dry-run", action="store_true", help="with --repair: show what would change")
    ap.add_argument("--scope", choices=[SCOPE_UNIVERSAL, SCOPE_ORCHESTRATOR, SCOPE_OPT_IN],
                    help="with --repair: only repair this scope")
    args = ap.parse_args()

    if args.list_in_scope:
        for cron in load_manifest():
            if is_in_scope(cron):
                print(cron.get("name", ""))
        return 0

    if args.repair:
        results = repair_all(scope_filter=args.scope, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                if r["action"] in ("updated", "created", "would-edit", "would-create"):
                    print(f"{r['action'].upper()} {r['detail']}")
                elif r["action"] == "error":
                    print(f"ERROR {r['detail']}")
        return 1 if any(r["action"] == "error" for r in results) else 0

    drifted, missing, orphans = check_drift()
    problems = drifted + missing

    if args.json:
        print(json.dumps({
            "drifted": [{**d, "diffs": d["diffs"]} for d in drifted],
            "missing": [m["name"] for m in missing],
            "orphans": orphans,
        }, indent=2))
    else:
        for d in drifted:
            print(f"DRIFT {d['name']}:")
            for diff in d["diffs"]:
                print(f"  - {diff}")
        for m in missing:
            print(f"MISSING {m['name']}")
        for o in orphans:
            print(f"ORPHAN {o}")
        if not problems and not orphans:
            print("OK: all in-scope crons match manifest")

    return 1 if (problems or orphans) and args.check else 0


if __name__ == "__main__":
    sys.exit(main())
