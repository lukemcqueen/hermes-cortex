#!/usr/bin/env python3
"""
fix-cron-duplicates.py — Fix duplicate cron jobs and naming violations.

Detects and repairs:
1. Duplicate pairs where old bare-name cron + new prefixed cron run the same script
2. Uninstall arrays that don't match create sections in install-crons.sh / install-orch-crons.sh
3. Crons missing from expected arrays that should be there

Usage:
    python3 fix-cron-duplicates.py                    # scan + report
    python3 fix-cron-duplicates.py --fix              # scan + fix
    python3 fix-cron-duplicates.py --dry-run          # what would change

This script is SAFE to run on any agent — it reads the local cron state,
compares against the repo install scripts, and reports/fixes drift.

Exit codes:
    0 = clean (no issues detected)
    1 = issues detected (if not --fix) or fix failures
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
REPO = Path(os.environ.get("CORTEX_REPO", HOME / "hermes-cortex"))
CRON_JOBS = HOME / ".hermes" / "cron" / "jobs.json"
INSTALL_CRONS = REPO / "ops" / "scripts" / "install-crons.sh"
INSTALL_ORCH_CRONS = REPO / "ops" / "scripts" / "install" / "install-orch-crons.sh"

# ── Known duplicate pairs (old → keep) ─────────────────────────
# These are crons where the old bare name + new prefixed name run the
# same script. The old name should be removed.
KNOWN_DUPLICATES = {
    "bus-audit-watchdog": "orch-bus-audit-watchdog",
    "bus-forwarder-sync": "orch-bus-forwarder-sync",
    "bus-recover-timeouts": "orch-bus-recover-timeouts",
    "bus-confirmation-poller": "orch-bus-confirmation-poller",
    "bus-confirmation-alert": "orch-bus-confirmation-alert",
}

# ── Expected bare names that should now be prefixed ─────────────
# These exist in create sections but need to be in uninstall arrays too.
# This dict maps old-uninstall-name → create_name or None if they match
# None = name appears in both create and uninstall (correct)
# string = uninstall name that should be renamed to create name


def load_cron_state() -> list[tuple[str, str, str]]:
    """Load running cron jobs from jobs.json."""
    if not CRON_JOBS.exists():
        print(f"  ✗ jobs.json not found: {CRON_JOBS}")
        return []
    try:
        data = json.loads(CRON_JOBS.read_text())
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        return [(j.get("name", ""), j.get("script", ""), j.get("job_id", ""))
                for j in jobs if isinstance(j, dict) and j.get("name")]
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ✗ Failed to read {CRON_JOBS}: {e}")
        return []


def read_uninstall_array(path: Path) -> list[str]:
    """Read cron names from the uninstall array in an install script."""
    if not path.exists():
        return []
    text = path.read_text()
    m = re.search(r'for job in \\\n(.*?); do', text, re.DOTALL)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


def write_uninstall_array(path: Path, names: list[str]) -> bool:
    """Replace the uninstall array in an install script with the given names."""
    if not path.exists():
        return False
    text = path.read_text()
    # Find the uninstall block
    m = re.search(r'for job in \\\n(.*?); do', text, re.DOTALL)
    if not m:
        return False
    old_block = m.group(1)
    # Build new block with quotes, backslash-newline every N items
    lines = []
    for i, name in enumerate(names):
        suffix = " \\" if i < len(names) - 1 else "; do"
        lines.append(f'    "{name}"{suffix}')
    new_block = "\n".join(lines) + "\n  "
    new_text = text[:m.start(1)] + new_block + text[m.end():]
    if new_text == text:
        return False  # No change
    path.write_text(new_text)
    # Verify bash syntax after writing
    import subprocess
    r = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        # Revert the change and warn
        path.write_text(text)  # restore original
        print(f"  ✗ BASH SYNTAX ERROR in {path.name}: {r.stderr[:200]}")
        print(f"    Change reverted. Fix the uninstall array generator and re-run.")
        return False
    return True


def read_create_names(path: Path) -> list[str]:
    """Read cron names from create_cron calls in an install script."""
    if not path.exists():
        return []
    text = path.read_text()
    # Match: create_cron "name" ...
    return re.findall(r'create_cron\s+"([^"]+)"', text)


def detect_duplicates(crons: list) -> list[tuple]:
    """Detect duplicate pairs running the same script."""
    # Build name → (job_id, script) map
    by_name = {}
    for name, script, jid in crons:
        by_name[name] = (jid, script)

    found = []
    for old_name, new_name in KNOWN_DUPLICATES.items():
        if old_name in by_name and new_name in by_name:
            old_jid, old_script = by_name[old_name]
            new_jid, new_script = by_name[new_name]
            # Check if they run the same script
            if old_script == new_script:
                found.append((old_name, new_name, old_jid, new_jid, old_script))
            else:
                print(f"  ⚠ {old_name} (script={old_script}) vs {new_name} (script={new_script}) — different scripts, not a duplicate")
    return found


def detect_missing_from_uninstall(crons: list) -> list[str]:
    """Detect crons that exist in create sections but not in uninstall arrays."""
    issues = []

    # Check install-crons.sh
    create_names = set(read_create_names(INSTALL_CRONS))
    uninstall_names = set(read_uninstall_array(INSTALL_CRONS))
    missing_in_uninstall = create_names - uninstall_names
    if missing_in_uninstall:
        for name in sorted(missing_in_uninstall):
            issues.append(f"  ✗ '{name}' in create_cron but NOT in uninstall array ({INSTALL_CRONS.name})")
    stale_in_uninstall = uninstall_names - create_names
    if stale_in_uninstall:
        for name in sorted(stale_in_uninstall):
            issues.append(f"  ⚠ '{name}' in uninstall array but NOT in any create_cron ({INSTALL_CRONS.name})")

    # Check install-orch-crons.sh
    orch_create = set(read_create_names(INSTALL_ORCH_CRONS))
    orch_uninstall = set(read_uninstall_array(INSTALL_ORCH_CRONS))
    orch_missing = orch_create - orch_uninstall
    if orch_missing:
        for name in sorted(orch_missing):
            issues.append(f"  ✗ '{name}' in create_cron but NOT in uninstall array ({INSTALL_ORCH_CRONS.name})")
    orch_stale = orch_uninstall - orch_create
    if orch_stale:
        for name in sorted(orch_stale):
            issues.append(f"  ⚠ '{name}' in uninstall array but NOT in any create_cron ({INSTALL_ORCH_CRONS.name})")

    return issues


def fix_duplicates(duplicates: list[tuple], dry_run: bool) -> int:
    """Remove the old duplicate cron jobs."""
    fixed = 0
    for old_name, new_name, old_jid, new_jid, script in duplicates:
        action = "[DRY-RUN] Would remove" if dry_run else "Removing"
        print(f"  {action} duplicate: {old_name} ({old_jid}) — {new_name} ({new_jid}) runs the same script '{script}'")
        if not dry_run:
            r = subprocess.run(
                [sys.executable, "-m", "hermes", "cron", "remove", "--force", old_name],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0 or "not found" in r.stderr.lower():
                print(f"    ✓ Removed {old_name}")
                fixed += 1
            else:
                print(f"    ✗ Failed to remove: {r.stderr[:200] or r.stdout[:200]}")
                # Fallback: direct jobs.json patch
                _remove_from_json(old_name)
                fixed += 1
    return fixed


def _remove_from_json(name: str):
    """Remove a cron from jobs.json directly (fallback if hermes CLI fails)."""
    if not CRON_JOBS.exists():
        return
    try:
        data = json.loads(CRON_JOBS.read_text())
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        new_jobs = [j for j in jobs if isinstance(j, dict) and j.get("name") != name]
        if len(new_jobs) < len(jobs):
            if isinstance(data, dict):
                data["jobs"] = new_jobs
            else:
                data = new_jobs
            CRON_JOBS.write_text(json.dumps(data, indent=2, default=str))
            print(f"    ✓ Removed {name} from jobs.json")
    except Exception as e:
        print(f"    ✗ Failed to patch jobs.json: {e}")


def fix_uninstall_arrays(dry_run: bool) -> int:
    """Fix uninstall arrays to match create sections."""
    fixed = 0

    # Fix install-crons.sh
    create_names = read_create_names(INSTALL_CRONS)
    create_set = set(create_names)
    current_uninstall = set(read_uninstall_array(INSTALL_CRONS))

    # Check if uninstall array needs updating
    if current_uninstall != create_set:
        uninstall_missing = create_set - current_uninstall
        uninstall_extra = current_uninstall - create_set
        if dry_run:
            if uninstall_missing:
                print(f"  [DRY-RUN] Would add to {INSTALL_CRONS.name} uninstall: {', '.join(sorted(uninstall_missing))}")
            if uninstall_extra:
                print(f"  [DRY-RUN] Would remove from {INSTALL_CRONS.name} uninstall: {', '.join(sorted(uninstall_extra))}")
        else:
            updated = write_uninstall_array(INSTALL_CRONS, sorted(create_set))
            if updated:
                print(f"  ✓ Updated uninstall array in {INSTALL_CRONS.name}")
                print(f"    Added: {', '.join(sorted(uninstall_missing)) if uninstall_missing else 'none'}")
                print(f"    Removed: {', '.join(sorted(uninstall_extra)) if uninstall_extra else 'none'}")
                fixed += 1
            else:
                print(f"  ⚠ No changes needed for {INSTALL_CRONS.name}")

    # Fix install-orch-crons.sh
    orch_create = set(read_create_names(INSTALL_ORCH_CRONS))
    orch_uninstall = set(read_uninstall_array(INSTALL_ORCH_CRONS))

    if orch_uninstall != orch_create:
        orch_missing = orch_create - orch_uninstall
        orch_extra = orch_uninstall - orch_create
        if dry_run:
            if orch_missing:
                print(f"  [DRY-RUN] Would add to {INSTALL_ORCH_CRONS.name} uninstall: {', '.join(sorted(orch_missing))}")
            if orch_extra:
                print(f"  [DRY-RUN] Would remove from {INSTALL_ORCH_CRONS.name} uninstall: {', '.join(sorted(orch_extra))}")
        else:
            updated = write_uninstall_array(INSTALL_ORCH_CRONS, sorted(orch_create))
            if updated:
                print(f"  ✓ Updated uninstall array in {INSTALL_ORCH_CRONS.name}")
                fixed += 1
            else:
                print(f"  ⚠ No changes needed for {INSTALL_ORCH_CRONS.name}")

    return fixed


def gc_orphans(dry_run: bool, do_prune: bool = False) -> int:
    """Scan for orphan crons not in any install script.
    With --prune, only removes no_agent crons whose deployed script is gone.
    LLM-driven crons and local-* crons are always preserved."""
    expected = set(read_uninstall_array(INSTALL_CRONS))
    expected |= set(read_uninstall_array(INSTALL_ORCH_CRONS))

    if not CRON_JOBS.exists():
        return 0
    try:
        data = json.loads(CRON_JOBS.read_text())
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        running = {j.get("name", ""): j for j in jobs if isinstance(j, dict) and j.get("name")}
    except (json.JSONDecodeError, OSError):
        return 0

    # Orphans: running but not expected
    orphans = {n for n in running if n not in expected}

    if not orphans:
        print("  ✓ No orphan crons found")
        return 0

    print(f"  Found {len(orphans)} orphan cron(s) not in any install script:")

    removed = 0
    for name in sorted(orphans):
        job = running[name]
        is_noagent = job.get("no_agent", False)
        is_local = name.startswith("local-")
        script = job.get("script", "") or ""
        # Check if deployed script file exists
        deploy_home = HOME / ".hermes-cortex"
        script_path = deploy_home / "scripts" / script if script else None
        script_exists = script_path.exists() if script_path else False

        context = []
        if is_local:
            context.append("local-only")
        if not is_noagent:
            context.append("LLM-driven")
        if script:
            context.append(f"script={'exists' if script_exists else 'GONE'}")
        ctx = f" ({', '.join(context)})" if context else ""

        # Safety: only prune no_agent orphans whose deployed script is gone
        can_prune = is_noagent and script and not script_exists and not is_local

        if do_prune and can_prune:
            action = "[DRY-RUN] Would remove" if dry_run else "Removing"
            print(f"    {action}: {name}{ctx}")
            if not dry_run:
                r = subprocess.run(
                    [sys.executable, "-m", "hermes", "cron", "remove", "--force", name],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode == 0 or "not found" in r.stderr.lower():
                    print(f"      ✓ Removed")
                    removed += 1
                else:
                    print(f"      ✗ CLI failed: {r.stderr[:100]}")
                    _remove_from_json(name)
                    removed += 1
        else:
            reason = " (kept: " + (
                "local-only" if is_local else
                "LLM-driven, can't determine intentionality" if not is_noagent else
                "script still exists, not orphaned" if script_exists else
                "use --prune to remove"
            ) + ")"
            print(f"    ⚠ {name}{ctx}{reason}")

    return removed


def main():
    dry_run = "--dry-run" in sys.argv
    do_fix = "--fix" in sys.argv
    do_gc = "--gc" in sys.argv
    do_prune = "--prune" in sys.argv

    if not REPO.exists():
        print(f"  ✗ Repo not found: {REPO}")
        sys.exit(2)

    mode = "SCAN ONLY"
    if do_fix:
        mode = "FIX"
    elif do_gc:
        mode = "GC" + (" + PRUNE" if do_prune else " (scan only)")
    mode_str = f"DRY RUN — {mode}" if dry_run else mode

    print(f"═══ Cron Duplicate Fixer ═══")
    print(f"  Repo: {REPO}")
    print(f"  Mode: {mode_str}")
    print()

    if do_gc:
        print("── Garbage Collection ──")
        removed = gc_orphans(dry_run, do_prune)
        print()
        if removed > 0:
            print(f"  Removed {removed} orphan cron(s)")
        sys.exit(0)

    crons = load_cron_state()
    print(f"  Loaded {len(crons)} cron jobs from {CRON_JOBS.name}")
    print()

    # ── Step 1: Detect duplicates ──
    print("── Step 1: Duplicate detection ──")
    duplicates = detect_duplicates(crons)
    if duplicates:
        print(f"  Found {len(duplicates)} duplicate pair(s):")
        for old_name, new_name, _, _, script in duplicates:
            print(f"    • {old_name} ↔ {new_name} (both: {script})")
    else:
        print("  ✓ No duplicates found")
    print()

    # ── Step 2: Check uninstall array drift ──
    print("── Step 2: Uninstall array alignment ──")
    drift_issues = detect_missing_from_uninstall(crons)
    if drift_issues:
        print(f"  Found {len(drift_issues)} issue(s):")
        for issue in drift_issues:
            print(f"  {issue}")
    else:
        print("  ✓ All create names match uninstall arrays")
    print()

    # ── Apply fixes ──
    if not do_fix:
        if duplicates or drift_issues:
            print(f"  Run with --fix to apply fixes")
            sys.exit(1)
        print("  ✓ Clean — no issues detected")
        sys.exit(0)

    print("── Applying fixes ──")
    fixed_dupes = fix_duplicates(duplicates, dry_run)
    fixed_arrays = fix_uninstall_arrays(dry_run)

    print()
    if fixed_dupes > 0 or fixed_arrays > 0:
        print(f"  Fixed: {fixed_dupes} duplicate(s) removed, {fixed_arrays} install array(s) aligned")
        print(f"  Next steps:")
        print(f"    1. Run: python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet")
        print(f"    2. Commit and push the install script changes")
        print(f"    3. On each agent, run this script again to verify")
    else:
        print("  Nothing to fix")

    sys.exit(0 if fixed_dupes == 0 and fixed_arrays == 0 else 1)


if __name__ == "__main__":
    main()
