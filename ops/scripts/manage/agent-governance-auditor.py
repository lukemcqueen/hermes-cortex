#!/usr/bin/env python3
from __future__ import annotations
"""
governance-auditor.py — no_agent watchdog: governance maintenance + unscored detection

Watchdog pattern:
 Empty stdout → silent (all changes scored)
 Text output → delivered to user (unscored changes found)

Scans repos under ~/Developer/ for files modified in the last N hours,
cross-references against the loop-governance DB, and reports any that
don't have a corresponding score-cycle entry.

QUIET when nothing to report — only produces output when unscored
changes are detected.
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from state_tracker import StateTracker
from typing import Optional


def _cron_ts(name: str) -> str:
  """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
  kst = datetime.now(timezone(timedelta(hours=9))).strftime(
    "[%Y-%m-%d %H:%M KST]"
  )
  return f"{kst} {name}:"


# ── Config ──────────────────────────────────────────────────
LOOKBACK_HOURS = int(os.environ.get("SCORE_AUDITOR_LOOKBACK", "24"))
MAX_FILES_SHOWN = 15
DB_PATH = os.path.expanduser(
  os.environ.get(
    "SCORE_DB_PATH",
    "~/.hermes-cortex/data/loop-governance.db"
  )
)
SCANNED_DIRS = [
  os.path.expanduser("~/Developer"),
  os.path.expanduser("~/hermes-cortex"),
  os.path.expanduser("~/Sites"),
  os.path.expanduser("~/Documents/ACME"),
]
EXCLUDE_PATTERNS = [
  "__pycache__", ".venv", "node_modules", ".git",
  ".hermes", ".hermes-cortex", ".next", "target",
  "vendor", ".bun", ".cache", "go/pkg",
  "test-results", "playwright-report",
]

# ── Helpers ──────────────────────────────────────────────────
HOME = os.path.expanduser("~")

def should_exclude(path: str) -> bool:
  """Check if path should be excluded from scanning."""
  parts = path.split(os.sep)
  return any(p in parts for p in EXCLUDE_PATTERNS)

def find_recent_files() -> list[dict]:
  """Find files modified in the lookback window across scanned dirs."""
  cutoff = time.time() - (LOOKBACK_HOURS * 3600)
  results = []

  for scan_dir in SCANNED_DIRS:
    if not os.path.isdir(scan_dir):
      continue

    try:
      for root, dirs, files in os.walk(scan_dir):
        # Prune excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_PATTERNS
              and not d.startswith(".git")
              and d not in ["node_modules", "__pycache__",
                     ".venv", ".next", "target",
                     "vendor", ".bun"]]

        for fname in files:
          fpath = os.path.join(root, fname)
          try:
            mtime = os.path.getmtime(fpath)
            if mtime < cutoff:
              continue
            # Only track source-like files
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (
              ".py", ".js", ".ts", ".tsx", ".jsx", ".rb",
              ".go", ".rs", ".java", ".kt", ".sh", ".bash",
              ".yaml", ".yml", ".json", ".toml", ".cfg",
              ".md", ".html", ".css", ".scss", ".sql",
              ".plist", ".conf", ".env.example", ".gitignore",
            ):
              continue

            # Check git tracking — only flag tracked files
            repo_root = _find_git_root(root)
            if repo_root:
              rel = os.path.relpath(fpath, repo_root)
              # Check if tracked in git
              r = subprocess.run(
                ["git", "-C", repo_root, "ls-files",
                 "--error-unmatch", rel],
                capture_output=True, text=True, timeout=5
              )
              if r.returncode != 0:
                continue # untracked file

              # Skip files that match HEAD — they were pulled,
              # not locally edited. Only flag dirty files.
              r2 = subprocess.run(
                ["git", "-C", repo_root, "diff", "--quiet",
                 "HEAD", "--", rel],
                capture_output=True, timeout=5,
              )
              if r2.returncode == 0:
                continue # clean vs HEAD → pulled, skip

            results.append({
              "path": fpath.replace(HOME, "~"),
              "mtime": datetime.fromtimestamp(mtime,
                              tz=timezone.utc),
              "repo": os.path.basename(repo_root) if repo_root
                  else "unknown",
            })
          except (OSError, subprocess.TimeoutExpired):
            continue
    except (OSError, PermissionError):
      continue

  return results

def _find_git_root(path: str) -> Optional[str]:
  """Walk up from path to find .git directory."""
  p = Path(path)
  for parent in [p] + list(p.parents):
    if (parent / ".git").exists():
      return str(parent)
  return None

def get_scored_tasks() -> set[str]:
  """Get task IDs from the loop-governance DB."""
  if not os.path.exists(DB_PATH):
    return set()

  try:
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Try different possible table schemas
    tables = cur.execute(
      "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]

    if 'loop_cycles' in table_names:
      rows = cur.execute(
        'SELECT DISTINCT task_id FROM loop_cycles'
      ).fetchall()
    elif 'cycles' in table_names:
      rows = cur.execute(
        'SELECT DISTINCT task_id FROM cycles'
      ).fetchall()
    elif 'cycle_scores' in table_names:
      rows = cur.execute(
        'SELECT DISTINCT task_id FROM cycle_scores'
      ).fetchall()
    else:
      return set()

    conn.close()
    return {r[0] for r in rows if r[0]}
  except Exception:
    return set()

# ── Stale lock cleanup ────────────────────────────────────────
GOVERNANCE_STATE_DIR = os.path.expanduser("~/.hermes-cortex/state")
LOCK_MAX_AGE_HOURS = 12


def _cleanup_stale_locks() -> list[str]:
  """Remove stale governance locks older than 12h.

  Only removes session-scoped locks (.governance-sess_*.json) that
  are past the staleness threshold. The generic fallback
  .governance-generic.json is never auto-removed (legacy format;
  no longer created by current MCP server or plugin).

  Returns list of human-readable cleanup messages (empty = nothing done).
  """
  if not os.path.isdir(GOVERNANCE_STATE_DIR):
    return []

  now = time.time()
  cleaned = []

  for fname in os.listdir(GOVERNANCE_STATE_DIR):
    if not fname.startswith(".governance-") or fname == ".governance-generic.json":
      continue
    fpath = os.path.join(GOVERNANCE_STATE_DIR, fname)
    if not os.path.isfile(fpath):
      continue

    age_hours = (now - os.path.getmtime(fpath)) / 3600
    if age_hours < LOCK_MAX_AGE_HOURS:
      continue

    # Read task info for the log
    task_info = ""
    try:
      with open(fpath) as f:
        d = json.load(f)
      task_info = f" (task={d.get('task_id','?')}, started={d.get('started_at','?')})"
    except Exception:
      task_info = "" # corrupt or unparseable lock — remove anyway with default info

    os.remove(fpath)
    cleaned.append(f" 🧹 Removed stale lock: {fname}{task_info} ({int(age_hours)}h old)")

  return cleaned


# ── Phase 4: Infrastructure integrity checks ────────────────────


def _check_infrastructure() -> list[str]:
  """Check that governance enforcement infrastructure is intact.

  Returns list of issue messages (empty = all good, silent).
  """
  issues = []

  # ── 1. Plugin deployment — prefer copy over symlink ──
  plugin_link = os.path.expanduser("~/.hermes/plugins/governance-enforcer")
  plugin_target = os.path.expanduser(
    "~/hermes-cortex/plugins/hermes-governance-enforcer"
  )

  if os.path.islink(plugin_link):
    actual_target = os.readlink(plugin_link)
    if actual_target != plugin_target:
      issues.append(
        f" 🛡️ Plugin symlink points to {actual_target}\n"
        f"    (expected {plugin_target}).\n"
        f"    Fix: cortex-update.sh (converts to copy)"
      )
    else:
      issues.append(
        f" 🛡️ Plugin is a symlink — should be a copy for chattr +i safety.\n"
        f"    Run: cortex-update.sh (converts automatically)"
      )
  elif os.path.isdir(plugin_link):
    # Already a copy — check it has the files
    init_py = os.path.join(plugin_link, "__init__.py")
    if not os.path.exists(init_py):
      issues.append(
        f" 🛡️ Plugin directory exists but __init__.py missing.\n"
        f"    Fix: cortex-update.sh "
      )
  else:
    issues.append(
      f" 🛡️ Governance plugin MISSING at {plugin_link}.\n"
      f"    Fix: cortex-update.sh "
    )

  # ── 2. Hook symlinks ──
  hooks_dir = os.path.expanduser("~/.hermes-cortex/hooks")
  expected_hooks = {
    "pre-commit": os.path.expanduser("~/.hermes-cortex/scripts/pre-commit-score"),
    "pre-push": os.path.expanduser("~/.hermes-cortex/scripts/pre-push-pull"),
    "post-commit": os.path.expanduser("~/.hermes-cortex/scripts/post-commit-audit"),
  }
  for hook_name, expected_target in expected_hooks.items():
    hook_path = os.path.join(hooks_dir, hook_name)
    if not os.path.islink(hook_path) and not os.path.isfile(hook_path):
      issues.append(
        f" 🔗 {hook_name} hook MISSING at {hook_path}.\n"
        f"    Fix: Run: cortex-update.sh "
      )
    elif os.path.islink(hook_path):
      actual = os.readlink(hook_path)
      if actual != expected_target:
        issues.append(
          f" 🔗 {hook_name} symlink points to {actual}\n"
          f"    (expected {expected_target}).\n"
          f"    Fix: ln -sf {expected_target} {hook_path}"
        )

  # ── 3. hooksPath config ──
  try:
    r = subprocess.run(
      ["git", "-C", os.path.expanduser("~/hermes-cortex"),
       "config", "--get", "core.hooksPath"],
      capture_output=True, text=True, timeout=5,
    )
    if r.returncode == 0:
      actual_hp = r.stdout.strip()
      expected_hp = hooks_dir
      if actual_hp != expected_hp:
        issues.append(
          f" ⚙️ core.hooksPath is '{actual_hp}'\n"
          f"    (expected '{expected_hp}').\n"
          f"    Fix: git config --global core.hooksPath {expected_hp}"
        )
    else:
      issues.append(
        f" ⚙️ core.hooksPath NOT SET.\n"
        f"    Fix: git config --global core.hooksPath {hooks_dir}"
      )
  except (subprocess.TimeoutExpired, FileNotFoundError):
    issues.append(" ⚙️ Could not check core.hooksPath (git not available).")

  # ── 4. Permissions ──
  perm_checks = [
    (os.path.expanduser("~/.hermes/plugins/governance-enforcer/__init__.py"), 0o444),
  ]
  for path, want in perm_checks:
    if os.path.exists(path) and not os.path.islink(path):
      try:
        have = os.stat(path).st_mode & 0o777
        if have != want:
          issues.append(
            f" 🔓 Permissions on {path}: {oct(have)}\n"
            f"    (expected {oct(want)}).\n"
            f"    Fix: chmod {oct(want)[2:]} {path}"
          )
      except OSError:
        continue # file removed between stat and chmod — skip gracefully

  # ── 5. Immutability ──
  immutable_targets = [
    os.path.expanduser("~/.hermes/plugins/governance-enforcer/__init__.py"),
    os.path.join(hooks_dir, "pre-commit"),
    os.path.join(hooks_dir, "pre-push"),
  ]
  for path in immutable_targets:
    if os.path.exists(path):
      try:
        r = subprocess.run(
          ["lsattr", path],
          capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
          flags = r.stdout.split()[0] if r.stdout else ""
          if "i" not in flags:
            issues.append(
              f" 🔓 Immutable flag MISSING on {path}.\n"
              f"    Fix: sudo chattr +i {path}"
            )
      except (subprocess.TimeoutExpired, OSError, IndexError):
        continue # lsattr failed or file removed — skip gracefully

  return issues


# ── Main ─────────────────────────────────────────────────────
def main() -> None:
  output = []

  # Phase 1: Clean stale governance locks
  lock_msgs = _cleanup_stale_locks()
  if lock_msgs:
    ts = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    output.append(f"[{ts}] governance-auditor: cleaned {len(lock_msgs)} stale lock(s)")
    output.extend(lock_msgs)
    output.append("")

  # Phase 1b: Check governance infrastructure integrity
  infra_msgs = _check_infrastructure()
  if infra_msgs:
    ts = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    output.append(f"[{ts}] governance-auditor: {len(infra_msgs)} infrastructure issue(s)")
    output.extend(infra_msgs)
    output.append("")

  # Phase 2: Check for unscored changes
  recent = find_recent_files()
  if not recent:
    StateTracker("governance-auditor").evaluate("healthy", has_issues=False)
    if output:
      print("\n".join(output))

  scored = get_scored_tasks()
  unscored: list[dict] = []
  now = datetime.now(timezone.utc)

  for f in recent:
    # Build expected task id patterns
    age_hours = (now - f["mtime"]).total_seconds() / 3600
    # If file was modified more than LOOKBACK_HOURS ago, skip
    if age_hours > LOOKBACK_HOURS:
      continue

    # Check if ANY scored task mentions this repo/file
    repo = f["repo"]
    basename = os.path.basename(f["path"])
    found = False
    for task_id in scored:
      if repo in task_id or basename in task_id:
        found = True
        break

    if not found:
      unscored.append(f)

  if not unscored:
    # Clear prior error state
    StateTracker("governance-auditor").evaluate("healthy", has_issues=False)
    if output:
      print("\n".join(output))
    return # silent or lock-cleanup only

  # State tracking — suppress duplicates
  hostname = os.uname().nodename.split(".")[0]
  fp = f"host={hostname}|count={len(unscored)}"
  action = StateTracker("governance-auditor").evaluate(fp)

  if action == "silent":
    return # same unscored count as last time

  # ── Report ──
  ts = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
  print(f"[{ts}] governance-auditor: {len(unscored)} unscored change(s)")
  print(f" Lookback: {LOOKBACK_HOURS}h | DB: {DB_PATH}")
  print("")

  # Group by repo
  by_repo: dict[str, list[dict]] = {}
  for f in unscored:
    by_repo.setdefault(f["repo"], []).append(f)

  for repo_name, files in sorted(by_repo.items()):
    print(f" 📁 {repo_name}/ ({len(files)} files)")
    shown = files[:MAX_FILES_SHOWN]
    for f in shown:
      mtime_local = f["mtime"].strftime("%H:%M %Z")
      print(f"   {f['path']} ({mtime_local})")
    remaining = len(files) - MAX_FILES_SHOWN
    if remaining > 0:
      print(f"   … and {remaining} more file(s)")
    print("")

  print(" 💡 Auto-remediating: running score-cycle on unscored files...")
  print("")

  # Phase 3: Auto-remediation — score unscoped files automatically
  scored_count = 0
  failed_count = 0
  for repo_name, files in sorted(by_repo.items()):
    # Gather all file paths for this repo
    repo_paths = []
    repo_root = ""
    for f in files:
      abs_path = os.path.expanduser(f["path"])
      # Find git root for this file
      candidate_repo = _find_git_root(abs_path)
      if candidate_repo and not repo_root:
        repo_root = candidate_repo
      if os.path.isfile(abs_path):
        repo_paths.append(abs_path)
    if not repo_paths or not repo_root:
      continue

    # Build a combined code file with all unscored files
    combined_code = ""
    for fp in repo_paths:
      try:
        with open(fp) as fh:
          rel = os.path.relpath(fp, repo_root)
          combined_code += f"# --- {rel} ---\n{fh.read()}\n\n"
      except (OSError, PermissionError):
        continue # can't read source file — skip for audit

    if not combined_code.strip():
      continue

    # Run score-cycle with the combined code
    repo_slug = os.path.basename(repo_root)
    task_id = f"auto-audit-{repo_slug}-{int(time.time())}"
    try:
      result = subprocess.run(
        ["score-cycle", "--task", task_id, "--cycle", "1",
         "--code", combined_code, "--pass-pct", "1.0", "--json"],
        capture_output=True, text=True, timeout=30,
      )
      if result.returncode == 0:
        scored_count += 1
        print(f"  ✅ {repo_slug}/: scored {len(repo_paths)} file(s) as task '{task_id}'")
      else:
        failed_count += 1
        print(f"  ❌ {repo_slug}/: score-cycle failed ({result.returncode})")
        # Log stderr for debugging
        if result.stderr:
          for line in result.stderr.strip().split("\n")[:3]:
            print(f"    {line}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
      failed_count += 1
      print(f"  ⚠ {repo_slug}/: cannot auto-score ({e})")

  print("")
  if scored_count > 0:
    print(f" ✅ Auto-scored {scored_count} repo(s) — changes now have governance records.")
  if failed_count > 0:
    print(f" ⚠ {failed_count} repo(s) could not be auto-scored. Manual scoring advised.")
  print("")

  # Exit 0 — watchdog pattern (output is the message)
  # Exit non-zero if we want the system to flag this as an error
  sys.exit(0)

if __name__ == "__main__":
  main()
