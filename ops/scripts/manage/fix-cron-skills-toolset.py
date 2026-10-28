#!/usr/bin/env python3
"""fix-cron-skills-toolset.py — give cron jobs the `skills` toolset they need.

THE CLASS (diagnosed 2026-10-26, cycle 13823; recurring since 2026-09-30):
a Hermes cron job that carries an EXPLICIT ``enabled_toolsets`` allowlist which
omits ``skills`` is never given a skill tool. The 7 always-section skills can
therefore never load, governance gate 1 blocks every write tool, and the job's
write-back silently never happens — while the job still reports success.

``skills`` is a real Hermes toolset; a per-job allowlist is authoritative over
``platform_toolsets.cron``, so the ONLY fix is that job's own config field.

WHY THIS SCRIPT RATHER THAN A CLI CALL: ``hermes cron edit`` exposes no
``--enabled-toolsets`` flag and the ``cronjob`` MCP tool is local to the host's
gateway, so the field is edited in the store directly, under the SAME
cross-process lock the gateway takes (``<cron dir>/.jobs.lock``), with an atomic
replace and a read-back verification.

SECOND CONDITION THIS SCRIPT REPORTS BUT NEVER AUTO-FIXES: an explicit allowlist
also excludes every MCP server unless it is named, so such a job cannot mint the
governance lock that a write INSIDE a governed repo requires (gate 2) — and a
write OUTSIDE every repo is refused outright ("No governed repo could be
resolved"). The measured working configuration for an unattended write-back job
is NO allowlist at all. Clearing one is a widening of the tool surface, so this
script names it and leaves the decision to the operator.

WHAT IT WILL NOT DO (deliberate, pinned by tests):
  * it never INVENTS an allowlist for a job that has none — such a job inherits
    ``platform_toolsets.cron`` and already has ``skills`` on a healthy host;
  * it never rewrites a job that already has ``skills``;
  * it never touches a ``no_agent`` job (no LLM session, so no skills gate);
  * it removes nothing: the proposed list is the current list plus ``skills``.

EXIT CODES (the fleet's three outcomes):
  0 = nothing to fix, or --apply succeeded and verified
  1 = findings (report mode only; nothing written)
  3 = COULD NOT VERIFY — the store is missing or unparseable, or the write did
      not verify. Never rendered as 0.

Usage:
  python3 fix-cron-skills-toolset.py                 # report only
  python3 fix-cron-skills-toolset.py --apply         # fix, then verify
  python3 fix-cron-skills-toolset.py --jobs-file <path>   # test seam
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REQUIRED_TOOLSET = "skills"

RC_OK = 0
RC_FINDINGS = 1
RC_COULD_NOT_VERIFY = 3


def default_jobs_file() -> Path:
    """The live cron store for this profile (HERMES_HOME-aware, never hardcoded)."""
    root = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(root) / "cron" / "jobs.json"


def _jobs(payload) -> list:
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    return jobs if isinstance(jobs, list) else []


def plan_fixes(payload) -> list:
    """Jobs that need `skills` added to an explicit allowlist.

    Returns a list of dicts: name, job_id, current, proposed. Pure: reads the
    parsed payload only, so it is safe to call before deciding to write.
    """
    out = []
    for job in _jobs(payload):
        if not isinstance(job, dict) or job.get("no_agent"):
            continue
        current = job.get("enabled_toolsets")
        if not isinstance(current, list) or not current:
            continue  # no allowlist: inherits platform_toolsets.cron
        if REQUIRED_TOOLSET in current:
            continue
        out.append({
            "name": job.get("name") or "?",
            "job_id": job.get("job_id") or "?",
            "current": list(current),
            "proposed": list(current) + [REQUIRED_TOOLSET],
        })
    return out


def apply_fixes(payload, plan) -> int:
    """Add the missing toolset to each planned job in the parsed payload."""
    by_id = {j.get("job_id"): j for j in _jobs(payload) if isinstance(j, dict)}
    changed = 0
    for item in plan:
        job = by_id.get(item["job_id"])
        if job is None:
            continue
        job["enabled_toolsets"] = list(item["proposed"])
        changed += 1
    return changed


def _read_payload(path: Path):
    """(payload, None) or (None, reason). utf-8-sig absorbs a BOM."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"{path} is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path} is not a JSON object"
    return payload, None


def _write_payload(path: Path, payload) -> None:
    """Atomic replace in the store's own directory (same filesystem)."""
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class _StoreLock:
    """The gateway's own cross-process lock for the cron store.

    ``cron/jobs.py`` flocks ``<cron dir>/.jobs.lock``; taking the same lock is
    what keeps a direct edit from being lost against a concurrent gateway write.
    Without fcntl the lock degrades to a printed warning rather than a silent
    no-op, and the write is still atomic (a torn read stays impossible — only a
    concurrent update could be lost).
    """

    def __init__(self, store: Path):
        self.lock_path = store.parent / ".jobs.lock"
        self._fd = None
        self.degraded = False

    def __enter__(self):
        try:
            import fcntl
        except ImportError:  # pragma: no cover — Windows
            self.degraded = True
            print(f"WARNING: fcntl unavailable — editing {self.lock_path.name} unlocked",
                  file=sys.stderr)
            return self
        self._fd = open(self.lock_path, "a+", encoding="utf-8")
        fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fd is not None:
            try:
                import fcntl
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            self._fd.close()
        return False


def _print_plan(plan) -> None:
    print(f"Jobs needing the '{REQUIRED_TOOLSET}' toolset: {len(plan)}")
    for item in plan:
        print(f"  {item['name']} ({item['job_id']})")
        print(f"    now      : {', '.join(item['current'])}")
        print(f"    proposed : {', '.join(item['proposed'])}")
    print("\nNOTE: adding 'skills' satisfies gate 1 only. An explicit allowlist also\n"
          "excludes every MCP server unless named, so a job that writes INSIDE a\n"
          "governed repo still cannot mint its lock (gate 2), and a write OUTSIDE\n"
          "every repo is refused outright. The measured working configuration for an\n"
          "unattended write-back job is no allowlist at all — clear it if this job's\n"
          "write-back must land; that is a widening, so this script will not do it.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs-file", default=str(default_jobs_file()),
                    help="cron store to inspect (default: $HERMES_HOME/cron/jobs.json)")
    ap.add_argument("--apply", action="store_true", help="write the fix, then verify it")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args(argv)

    store = Path(args.jobs_file).expanduser()
    if not store.is_file():
        print(f"COULD NOT VERIFY: no cron store at {store}", file=sys.stderr)
        return RC_COULD_NOT_VERIFY

    payload, reason = _read_payload(store)
    if payload is None:
        print(f"COULD NOT VERIFY: {reason}", file=sys.stderr)
        return RC_COULD_NOT_VERIFY

    plan = plan_fixes(payload)
    if args.json:
        print(json.dumps({"store": str(store), "findings": plan}, indent=2))
    elif plan:
        _print_plan(plan)
    else:
        print(f"nothing to fix in {store} — no LLM cron carries an allowlist without "
              f"'{REQUIRED_TOOLSET}'")

    if not plan:
        return RC_OK
    if not args.apply:
        print(f"\n(report only — re-run with --apply to add '{REQUIRED_TOOLSET}')")
        return RC_FINDINGS

    with _StoreLock(store) as lock:
        # Re-read UNDER the lock: a gateway write between our first read and now
        # would otherwise be lost by our replace.
        payload, reason = _read_payload(store)
        if payload is None:
            print(f"COULD NOT VERIFY: {reason}", file=sys.stderr)
            return RC_COULD_NOT_VERIFY
        plan = plan_fixes(payload)
        if not plan:
            print("nothing to fix after re-reading under the lock")
            return RC_OK
        changed = apply_fixes(payload, plan)
        try:
            _write_payload(store, payload)
        except OSError as exc:
            print(f"COULD NOT VERIFY: write failed: {exc}", file=sys.stderr)
            return RC_COULD_NOT_VERIFY
        if lock.degraded:
            print("NOTE: written without the cross-process lock (fcntl unavailable)")

    # Verify by reading the file back — the write is a claim until it is read.
    payload, reason = _read_payload(store)
    if payload is None:
        print(f"COULD NOT VERIFY after write: {reason}", file=sys.stderr)
        return RC_COULD_NOT_VERIFY
    still = plan_fixes(payload)
    if still:
        names = ", ".join(i["name"] for i in still)
        print(f"COULD NOT VERIFY: {len(still)} job(s) still lack '{REQUIRED_TOOLSET}' "
              f"after the write: {names}", file=sys.stderr)
        return RC_COULD_NOT_VERIFY

    print(f"\nFIXED {changed} job(s) in {store} — verified by read-back. The scheduler "
          f"reads this store on its next tick.")
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
