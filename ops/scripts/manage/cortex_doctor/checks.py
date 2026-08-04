"""
Checks — all health check functions for cortex-doctor.

Each check_* function accepts a Results object and appends results.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
  HOME,
  IS_MAC,
  IS_LINUX,
  CORTEX_REPO,
  CORTEX_HOME,
  HERMES_HOME,
  JOBS_FILE,
  CORTEX_ENV,
  LEGACY_MODELS_ENV,
  CONFIG_FILE,
  INSTALL_CRONS,
  INSTALL_ORCH_CRONS,
  INSTALL_SCRIPT,
  INSTALL_OLLAMA,
  SYMLINK_AUDIT,
  MCP_SERVERS_DIR,
  CURL,
  EXPECTED_MCP_SERVERS,
  ORCH_ONLY_MCP_SERVERS,
  EXTERNAL_SERVICES,
  CORE_FOOTPRINT,
  AGENT_ROLE,
  parse_expected_crons,
  parse_orch_crons,
  find_script_consumers,
)
from .helpers import run, run_bg, http_get, read_file, process_running, find_similar_name
from .results import Results


def _read_config_from_bus_conf(key: str) -> str:
  """Read a value from cortex-bus.conf by key. Returns '' if not found."""
  conf_path = CORTEX_HOME / "cortex-bus.conf"
  if not conf_path.exists():
    return ""
  try:
    for line in conf_path.read_text().splitlines():
      if line.startswith(f"{key}="):
        val = line.split("=", 1)[1].strip().strip("\"'")
        return val
  except OSError:
    log.warning("Could not read config file: %s", CONFIG_FILE)
  return ""


def check_repo(res: "Results") -> None:
  """1. Repo integrity: on main, clean, up to date."""
  if not CORTEX_REPO.is_dir():
    res.add(
      "Repo exists", "FAIL", f"Not found at {CORTEX_REPO}",
      "Set CORTEX_REPO env var or clone to ~/hermes-cortex",
    )
    return
  if not (CORTEX_REPO / ".git").is_dir():
    res.add("Repo git", "FAIL", "Not a git repository", "Run: git init or git clone")
    return

  branch = run_bg(["git", "-C", str(CORTEX_REPO), "rev-parse", "--abbrev-ref", "HEAD"])
  if branch == "main":
    res.add("Repo branch", "PASS", f"on '{branch}'")
  else:
    res.add("Repo branch", "WARN", f"on '{branch}' not 'main'", "Run: git checkout main")

  status = run_bg(["git", "-C", str(CORTEX_REPO), "status", "--porcelain"])
  if not status:
    res.add("Repo clean", "PASS")
  else:
    lines = status.count("\n") + 1
    res.add("Repo clean", "WARN", f"{lines} uncommitted change(s)", "Run: git status to review")

  run(["git", "-C", str(CORTEX_REPO), "fetch", "origin", "--quiet"], timeout=15)
  behind = run_bg(["git", "-C", str(CORTEX_REPO), "rev-list", "--count", "HEAD..origin/main"])
  if behind and behind != "0":
    res.add("Repo sync", "WARN", f"{behind} commit(s) behind origin/main", "REQUIRED: git pull --rebase")
  else:
    res.add("Repo sync", "PASS", "up to date with origin/main")

  hermes_agents = Path.home() / ".hermes" / "AGENTS.md"
  repo_agents = CORTEX_REPO / "AGENTS.md"

  # ── Deploy sync: is git HEAD deployed to runtime? ──
  update_commit_file = CORTEX_HOME / "state" / "update-commit"
  if update_commit_file.exists():
    deployed_commit = update_commit_file.read_text().strip()
    head_commit = run_bg(["git", "-C", str(CORTEX_REPO), "rev-parse", "HEAD"])
    if deployed_commit and head_commit and deployed_commit != head_commit:
      n_new = run_bg(["git", "-C", str(CORTEX_REPO), "rev-list", "--count", f"{deployed_commit}..HEAD"])
      res.add("Deploy sync", "FAIL",
          f"HEAD ({head_commit[:12]}) ahead of last deploy ({deployed_commit[:12]}) — {n_new or '?'} commit(s) not deployed",
          "REQUIRED: Run: cortex-update.sh ")
    else:
      res.add("Deploy sync", "PASS", "deployed commit matches HEAD")
  else:
    res.add("Deploy sync", "WARN", "state/update-commit not found — deploy status unknown",
        "Run: cortex-update.sh (creates state/update-commit)")

  hermes_agents = Path.home() / ".hermes" / "AGENTS.md"
  if not hermes_agents.exists():
    res.add("AGENTS.md (~/.hermes)", "FAIL", "~/.hermes/AGENTS.md missing",
        "REQUIRED: cp ~/hermes-cortex/AGENTS.md ~/.hermes/AGENTS.md  ⚠️  Merges local-only content — check diff ~/.hermes/AGENTS.md ~/hermes-cortex/AGENTS.md before overwriting")
    return
  # Size check: warn if >15K, fail if >20K (like SOUL.md does)
  agents_size = hermes_agents.stat().st_size
  if agents_size > 20480:
    res.add("AGENTS.md size", "FAIL",
        f"{agents_size/1024:.0f}K — exceeds 20K maximum",
        "REQUIRED: cp ~/hermes-cortex/AGENTS.md ~/.hermes/AGENTS.md  ⚠️  Backs up local-only content to ~/.hermes/AGENTS.md.local")
    return
  elif agents_size > 15360:
    res.add("AGENTS.md size", "WARN",
        f"{agents_size/1024:.0f}K — target <15K for optimal loading",
        "Run: diff ~/.hermes/AGENTS.md ~/hermes-cortex/AGENTS.md | head -50  then cp if safe  (⚠️  preserves customizations)")
  # Content check: extract all bold markers for comparison (like SOUL.md does)
  # ~/.hermes/AGENTS.md guides agent behavior — when working in this repo,
  # it should have the same content rules as the repo copy.
  repo_agents = CORTEX_REPO / "AGENTS.md"
  if repo_agents.exists():
    local_markers = _extract_agents_markers(hermes_agents)
    repo_markers = _extract_agents_markers(repo_agents)

    # Filter out the ⚠️ admonition marker (not a real rule)
    effective_repo = {m for m in repo_markers if not m.startswith("\u26a0\ufe0f")}

    # Allow agents to customize up to 2 markers (e.g. remove one rule, add one local note)
    missing = effective_repo - local_markers
    if len(missing) > 2:
      res.add("AGENTS.md sync", "FAIL",
          f"Local missing {len(missing)} content markers from template — "
          f"e.g. '{list(sorted(missing))[:3]}'",
          "REQUIRED: cp ~/hermes-cortex/AGENTS.md ~/.hermes/AGENTS.md  ⚠️  Backs up local-only content to ~/.hermes/AGENTS.md.local")
    else:
      res.add("AGENTS.md sync", "PASS")

  # Private repo migration check
  _private = HOME / "hermes-cortex-private"
  _agent_inbox = HOME / "agent-inbox-private"
  if _private.is_dir():
    if (_private / ".git").is_dir():
      res.add("Private repo", "WARN",
          "~/hermes-cortex-private still has .git — migrate to ~/private-data/",
          "mv ~/hermes-cortex-private ~/private-data && rm -rf ~/private-data/.git")
    else:
      res.add("Private repo", "INFO", "~/hermes-cortex-private migrated (no .git)")
  if _agent_inbox.is_dir():
    res.add("Private repo", "WARN",
        "~/agent-inbox-private still exists — file-based inbox is dead",
        "rm -rf ~/agent-inbox-private")


def check_dev_repo_agents(res: "Results") -> None:
  """1b. Development repos: check each project-level git repo has an AGENTS.md."""
  if not CORTEX_REPO.is_dir():
    return

  try:
    raw = subprocess.run(
      ["find", str(HOME), "-maxdepth", "3", "-name", ".git", "-type", "d"],
      capture_output=True, text=True, timeout=15,
    ).stdout.strip()
  except (subprocess.TimeoutExpired, OSError):
    res.add("Dev repo AGENTS.md", "INFO", "could not scan home directory for git repos")
    return

  if not raw:
    return

  EXCLUDED = {
    HOME / ".git",
    HOME / ".oh-my-zsh",
    HOME / ".hermes",
    HOME / ".brain",
    HOME / "brain",
    HOME / "gbrain",
    HOME / "__MACOSX",
    HOME / "Desktop",
    HOME / "Documents",
    HOME / "Downloads",
    HOME / "Music",
    HOME / "Pictures",
    HOME / "Videos",
    HOME / "Library",
    HOME / "Public",
    HOME / "Templates",
    HOME / "backups",
    HOME / "docker-data",
    HOME / "langfuse",
  }

  found_repos = []
  for path in raw.split("\n"):
    path = path.strip()
    if not path:
      continue
    repo_dir = Path(path).parent.resolve()
    skip = any(str(repo_dir).startswith(str(excl)) for excl in EXCLUDED)
    if skip or repo_dir == CORTEX_REPO:
      continue
    found_repos.append(repo_dir)

  if not found_repos:
    return

  present = []
  for repo in sorted(found_repos):
    agents_path = repo / "AGENTS.md"
    if agents_path.exists():
      present.append(repo.name)
    else:
      res.add(f"AGENTS.md ({repo.name})", "WARN",
          "missing AGENTS.md in dev repo",
          f"Create: touch ~/{repo.name}/AGENTS.md then add agent guidelines for this project")

  for repo in found_repos:
    agents_path = repo / "AGENTS.md"
    if not agents_path.exists():
      continue
    try:
      git_ts = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%ct", "HEAD"],
        capture_output=True, text=True, timeout=5,
      ).stdout.strip()
      file_mtime = agents_path.stat().st_mtime
      if git_ts and git_ts.isdigit():
        last_commit = int(git_ts)
        age_days = (file_mtime - last_commit) / 86400
        if age_days < -1:
          res.add(f"AGENTS.md ({repo.name})", "FAIL",
              "stale — last modified before latest commit — must be updated",
              f"REQUIRED: Review and update: ~/{repo.name}/AGENTS.md. "
              f"Run: cd ~/{repo.name} && git diff HEAD~5..HEAD --name-only -- AGENTS.md | head -20 "
              f"to see what's changed. Merge recent patterns into AGENTS.md.")
    except (subprocess.TimeoutExpired, OSError, ValueError):
      continue # git or stat failed — skip AGENTS.md age check for this repo


def _extract_agents_markers(path: Path) -> set:
  """Extract all content-bearing bold markers from an AGENTS.md file.

  Handles three formats:
    - Blockquote rules:  > **RULE N: TITLE**
    - Bullet principles: - **Title:** description
    - Numbered items:    N. **Title** — description

  Returns a set of bold-marker strings (e.g. 'RULE 1: LOAD TASK-START FIRST',
  'Two-repo system', 'Real execution, no simulation')."""
  if not path.exists():
    return set()
  text = path.read_text()
  # Strip YAML frontmatter if present (AGENTS.md doesn't have it, but be safe)
  main_start = 0
  if text.startswith('---'):
    end = text.find('---', 3)
    if end != -1:
      main_start = end + 3
  content = text[main_start:]

  markers = set()
  for line in content.split('\n'):
    # Format 1: > **BOLD TEXT** (blockquote rules — e.g. > **RULE 1: TITLE**)
    bm = re.search(r'^>\s+\*\*([^*]+)\*\*', line)
    if bm:
      markers.add(bm.group(1).strip())
      continue
    # Format 2: - **BOLD TEXT** (bullet architecture principles)
    bm = re.search(r'^\s*-\s+\*\*([^*]+)\*\*', line)
    if bm:
      markers.add(bm.group(1).strip())
      continue
    # Format 3: N. **BOLD TEXT** (numbered execution contract items)
    bm = re.search(r'^\s*\d+\.\s+\*\*([^*]+)\*\*', line)
    if bm:
      markers.add(bm.group(1).strip())
  return markers


def _extract_soul_markers(path: Path) -> set:
  """Extract all bold-marker sub-points from a SOUL.md file (across all sections).
  Returns a set of marker strings (e.g. 'Do real work', 'Proactive', 'Orchestrator')."""
  if not path.exists():
    return set()
  text = path.read_text()
  # Find the content after the frontmatter/YAML header (--- ... ---)
  main_start = 0
  if text.startswith('---'):
    end = text.find('---', 3)
    if end != -1:
      main_start = end + 3
  content = text[main_start:]
  # Extract all **bold** markers from list items anywhere in the file
  markers = set()
  for line in content.split('\n'):
    # Match: - **Marker** — description
    bm = re.search(r'^\s*-\s+\*\*([^*]+)\*\*', line)
    if bm:
      markers.add(bm.group(1).strip())
  return markers


def _extract_soul_principle_titles(path) -> dict:
    """Extract '### N. Title' principle headings from a SOUL.md.

    Returns {number: title} for every principle heading (canonical 1-12
    plus any local 13+). Tier headers ('### Tier N — …') are not principles.
    """
    titles = {}
    if not path.exists():
        return titles
    for line in path.read_text().splitlines():
        m = re.match(r'^###\s+(\d+)\.\s+(.+)$', line.strip())
        if m:
            titles[int(m.group(1))] = m.group(2).strip()
    return titles


def _soul_title_key(title: str) -> str:
    """Normalize a principle title for matching (number-agnostic, lowercase)."""
    return re.sub(r'^#{3,4}\s*\d+\.\s*', '', title).strip().lower()


def check_soul_sync(res):
  """Check SOUL.md is synced from repo template — for ALL agents."""
  template = CORTEX_REPO / "docs" / "templates" / "SOUL.md"
  if not template.exists():
    res.add("SOUL.md template", "WARN", "template not found at docs/templates/SOUL.md",
        "REQUIRED: verify repo is up to date")
    return

  hostname = os.uname().nodename.split('.')[0] # e.g. 'esther' or 'gisu'
  hermes_soul = Path.home() / ".hermes" / "SOUL.md"
  if not hermes_soul.exists():
    res.add("SOUL.md (~/.hermes)", "FAIL", "not found at ~/.hermes/SOUL.md",
        "REQUIRED: cp ~/hermes-cortex/docs/templates/SOUL.md ~/.hermes/SOUL.md")
    return

  # Size check: warn if >15K, fail if >20K
  size_bytes = hermes_soul.stat().st_size
  size_kb = size_bytes / 1024
  if size_bytes > 20480:
    res.add("SOUL.md (~/.hermes)", "FAIL",
        f"{size_kb:.0f}K — exceeds 20K maximum",
        "Trim content: remove deprecated sections, consolidate verbose entries")
    return
  elif size_bytes > 15360:
    res.add("SOUL.md (~/.hermes)", "WARN",
        f"{size_kb:.0f}K — target <15K for optimal loading",
        "Trim: keep scripture gleanings short (full study lives in ~/brain/<agent>/bible/); archive old entries")

  soul_text = hermes_soul.read_text()

  # Placeholder identity WARN — deployed copy still ships the template stub
  if "[your agent's name]" in soul_text or "Replace with your identity" in soul_text:
    res.add("SOUL.md identity (~/.hermes)", "WARN",
        "Identity still uses the template placeholder",
        "Replace 'You are [your agent's name]' with your real identity (hostname-derived)")

  # ── Canonical 12 principles (title-based) ──────────────────────────
  template_titles = _extract_soul_principle_titles(template)
  agent_titles = _extract_soul_principle_titles(hermes_soul)
  template_by_key = {_soul_title_key(t): n for n, t in template_titles.items()}
  agent_by_key = {_soul_title_key(t): n for n, t in agent_titles.items()}

  # Every canonical principle must be present in the deployed copy
  missing_canonical = [t for k, t in [(k, t) for t in template_titles.values()
                                      for k in [template_by_key.get(_soul_title_key(t), t)]]
                       if _soul_title_key(t) not in agent_by_key]
  if missing_canonical:
    res.add("SOUL.md canonical 12 (~/.hermes)", "FAIL",
        f"Missing {len(missing_canonical)} canonical principle(s): {', '.join(sorted(missing_canonical)[:5])}",
        "REQUIRED: Run: python3 ~/hermes-cortex/ops/scripts/manage/soul-merge.py")
  else:
    res.add("SOUL.md canonical 12 (~/.hermes)", "PASS",
        f"all {len(template_titles)} canonical principles present")

  # ── Local principles (0-12, generic, no duplicates) ────────────────
  local_titles = [t for t in agent_titles.values()
                  if _soul_title_key(t) not in template_by_key]
  dup_local = [t for t in local_titles
               if any(_soul_title_key(t) == _soul_title_key(ct)
                      for ct in template_titles.values())]
  if dup_local:
    res.add("SOUL.md local principles (~/.hermes)", "FAIL",
        f"Local principle(s) duplicate canonical set: {', '.join(sorted(dup_local)[:5])}",
        "Remove or rename; local principles must not duplicate the canonical 12")
  elif len(local_titles) > 12:
    res.add("SOUL.md local principles (~/.hermes)", "WARN",
        f"{len(local_titles)} local principle(s) — max 12 allowed",
        "Consolidate local principles into the canonical set or trim to ≤12")
  elif local_titles:
    res.add("SOUL.md local principles (~/.hermes)", "PASS",
        f"{len(local_titles)} local principle(s) — allowed (≤12, generic, non-duplicating)")
  else:
    res.add("SOUL.md local principles (~/.hermes)", "PASS", "none (0 allowed)")

  # ── Scripture brevity ──────────────────────────────────────────────
  # Gleanings must be SHORT; the full study lives in ~/brain/<agent>/bible/.
  # Warn above ~2.5K chars (roughly 3 entries — matches the cron's archive rule).
  m_sc = re.search(r'## Scripture Insights\n(.*?)(?=\n## )', soul_text, re.S)
  scripture_len = len(m_sc.group(1)) if m_sc else 0
  if scripture_len > 2500:
    res.add("SOUL.md scripture (~/.hermes)", "WARN",
        f"Scripture Insights ~{scripture_len//1024}K chars — gleanings should be short",
        "Archive old entries to ~/brain/<agent>/bible/archive/SOUL-archive.md; keep ~1-2 in SOUL.md")

  # ── Trait marker sync (Core Traits bullets) ────────────────────────
  template_markers = _extract_soul_markers(template)
  agent_markers = _extract_soul_markers(hermes_soul)
  orchestrators = {"moses", "esther"}
  is_orchestrator = hostname in orchestrators
  effective_template = template_markers

  if len(effective_template) > len(agent_markers) + 2:
    missing = len(template_markers) - len(agent_markers)
    res.add("SOUL.md template sync (~/.hermes)", "FAIL",
        f"Template has {len(template_markers)} trait markers, local has {len(agent_markers)} — {missing} missing",
        "REQUIRED: Run: python3 ~/hermes-cortex/ops/scripts/manage/soul-merge.py")
  elif len(agent_markers) < len(effective_template):
    missing_markers = effective_template - agent_markers
    critical_missing = {m for m in missing_markers
              if not any(skip in m for skip in
                    ["This principle absorbs", "Template verse", "Replace with"])}
    if critical_missing:
      res.add("SOUL.md template sync (~/.hermes)", "FAIL",
          f"Missing {len(critical_missing)} trait markers: {', '.join(sorted(critical_missing)[:5])}",
          "REQUIRED: Run: python3 ~/hermes-cortex/ops/scripts/manage/soul-merge.py")
    else:
      res.add("SOUL.md template sync (~/.hermes)", "PASS")
  else:
    res.add("SOUL.md template sync (~/.hermes)", "PASS")

  # Reverse drift: deployed has trait markers not in template. Diff against
  # the FULL template — filtering "Orchestrator" out then diffing made every
  # faithful non-orch copy a false WARN. Orchestrators may carry it locally;
  # non-orchestrators claiming it is a real defect.
  extra_in_deployed = agent_markers - template_markers
  if extra_in_deployed:
    skip_patterns = ["Scripture", "Bible", "Scripture Insights",
                     "Replace with", "your agent", "your purpose",
                     "your name", "your mission"]
    if is_orchestrator:
      skip_patterns.append("Orchestrator")  # orch may carry it locally
    real_extra = {m for m in extra_in_deployed
           if not any(skip in m for skip in skip_patterns)}
    if "Orchestrator" in extra_in_deployed and not is_orchestrator:
      res.add("SOUL.md orchestrator claim (~/.hermes)", "WARN",
          "Deployed claims the Orchestrator trait — you are NOT an orchestrator",
          "Remove the Orchestrator trait from Core Traits; orchestrator status is host-derived (moses/esther only)")
    elif real_extra:
      res.add("SOUL.md reverse drift (~/.hermes)", "WARN",
        f"Deployed has {len(real_extra)} markers not in template: {', '.join(sorted(real_extra)[:5])}",
        "Copy new principles to docs/templates/SOUL.md so all agents get them.")
    else:
      res.add("SOUL.md reverse drift (~/.hermes)", "PASS")
  else:
    res.add("SOUL.md reverse drift (~/.hermes)", "PASS")


def check_skills(res):
  """2. Skills manifest: skills.yaml exists, valid YAML, has required always skills."""
  skills_yaml = CORTEX_HOME / "skills.yaml"
  template_yaml = CORTEX_REPO / "docs" / "templates" / "skills.yaml"

  if not skills_yaml.exists():
    res.add("Skills manifest", "FAIL", f"Not found at {skills_yaml}",
        "Run: cp docs/templates/skills.yaml ~/.hermes-cortex/skills.yaml")
    return

  try:
    import yaml
    with open(skills_yaml) as f:
      data = yaml.safe_load(f)
  except ImportError:
    content = skills_yaml.read_text()
    if "always:" not in content or "on_task:" not in content:
      res.add("Skills manifest", "FAIL", "Missing 'always' or 'on_task' sections",
          f"Compare with template: {template_yaml}")
      return
    res.add("Skills manifest (basic)", "PASS", f"found at {skills_yaml}")
    return
  except (yaml.YAMLError, OSError) as e:
    res.add("Skills manifest", "FAIL", f"YAML parse error: {e}",
        f"Check syntax: python3 -c \"import yaml; yaml.safe_load(open('{skills_yaml}'))\"")
    return

  if not isinstance(data, dict):
    res.add("Skills manifest", "FAIL", "Root is not a mapping",
        "Check YAML structure has 'always:' at root")
    return

  always = data.get("always", [])
  on_task = data.get("on_task", {})

  required = [
    "task-start", "agent-flow", "reasoning-patterns", "reflexion-check",
    "change-checklist", "survey-before-action", "cortex-preflight", "agent-contract",
  ]
  always_names = {s.get("name") if isinstance(s, dict) else s for s in (always or [])}
  missing = [r for r in required if r not in always_names]

  if missing:
    res.add("Skills manifest: always", "FAIL",
        f"Missing required skills: {', '.join(missing)}",
        f"Add to always section: cp {template_yaml} {skills_yaml}")
  else:
    res.add("Skills manifest: always", "PASS", f"all {len(required)} required skills present")

  expected_on_task = {"debug", "review", "planning", "enterprise"}
  on_task_keys = set(on_task.keys()) if isinstance(on_task, dict) else set()
  missing_on = expected_on_task - on_task_keys
  if missing_on:
    res.add("Skills manifest: on_task", "WARN",
        f"Missing classifications: {', '.join(sorted(missing_on))}",
        f"Add on_task entries for these agent-flow patterns")
  else:
    res.add("Skills manifest: on_task", "PASS", "covers debug, review, planning, enterprise")

  if template_yaml.exists() and skills_yaml.exists():
    tmpl_mtime = template_yaml.stat().st_mtime
    skills_mtime = skills_yaml.stat().st_mtime
    if tmpl_mtime > skills_mtime + 1:
      res.add("Skills manifest: template", "WARN",
          "Template is newer than deployed manifest",
          f"Run: cp {template_yaml} {skills_yaml}")

  all_skill_names = set(always_names)
  if isinstance(on_task, dict):
    for skills_list in on_task.values():
      for s in skills_list:
        if isinstance(s, dict):
          all_skill_names.add(s.get("name", ""))
        elif isinstance(s, str):
          all_skill_names.add(s)
  all_skill_names.discard("")

  missing_skills = []
  skills_dir = HERMES_HOME / "skills"
  for name in sorted(all_skill_names):
    # Check flat path first, then search within category subdirectories
    skill_path = skills_dir / name
    if skill_path.exists():
      continue
    # Search category subdirectories: skills/*/<name>/
    found = False
    if skills_dir.is_dir():
      for cat_dir in skills_dir.iterdir():
        if cat_dir.is_dir() and (cat_dir / name).is_dir():
          found = True
          break
    if found:
      continue
    # Check repo skills with category subdirectory search
    repo_skills = CORTEX_REPO / "skills"
    found_repo = False
    if repo_skills.is_dir():
      for cat_dir in repo_skills.iterdir():
        if cat_dir.is_dir() and (cat_dir / name).is_dir():
          found_repo = True
          break
    if not found_repo:
      # Also check flat path in repo as fallback
      if (repo_skills / name).is_dir():
        found_repo = True
    if not found_repo:
      missing_skills.append(name)

  if missing_skills:
    res.add("Skills manifest: disk check", "WARN",
        f"{len(missing_skills)} skill(s) listed but not found on disk: {', '.join(missing_skills[:5])}",
        f"Run: hermes skills update or check ~/.hermes/skills/")
  else:
    res.add("Skills manifest: disk check", "PASS",
        f"all {len(all_skill_names)} skills found on disk")


def check_crons(res):
  """2. Cron audit: all expected crons registered, workdirs valid, run status, extra crons."""
  if not JOBS_FILE.exists():
    res.add("Crons file", "FAIL", f"Not found at {JOBS_FILE}", "Run: bash install-crons.sh")
    return

  try:
    data = json.loads(JOBS_FILE.read_text())
  except (json.JSONDecodeError, OSError) as e:
    res.add("Crons file", "FAIL", f"Parse error: {e}", "Check ~/.hermes/cron/jobs.json")
    return

  jobs = data.get("jobs", []) if isinstance(data, dict) else data
  registered = {j.get("name"): j for j in jobs if isinstance(j, dict) and j.get("name")}

  expected_crons = parse_expected_crons()
  if not expected_crons:
    res.add("Crons registry", "WARN", "Could not parse install-crons.sh",
        "Check ops/scripts/install-crons.sh exists")
    expected_crons = list(registered.keys())

  missing = []
  bad_workdir = []
  stale = []
  for name in expected_crons:
    job = registered.get(name)
    if not job:
      missing.append(name)
      continue
    wd = job.get("workdir", "")
    if wd and not os.path.isabs(wd):
      bad_workdir.append((name, wd))
    last_status = job.get("last_status", "")
    if last_status and last_status != "ok":
      stale.append((name, last_status))

  if not missing and not bad_workdir and not stale:
    res.add("Crons registered", "PASS", f"all {len(expected_crons)} expected crons present and healthy")
  else:
    if missing:
      res.add("Crons missing", "FAIL", f"{len(missing)} missing: {', '.join(missing)}",
          "Run: bash install-crons.sh --force")
    if bad_workdir:
      for name, wd in bad_workdir[:3]:
        res.add(f"Cron workdir ({name})", "FAIL", f"not absolute: '{wd}'",
            f"Re-create cron with absolute path")
    if stale:
      for name, st in stale[:3]:
        res.add(f"Cron status ({name})", "WARN", f"last run: {st}",
            f"Check: hermes cron logs --name {name}")
      if len(stale) > 3:
        res.add(f"Cron status ({len(stale)} total)", "WARN", "unhealthy crons",
            "Inspect and re-create unhealthy crons")

  orphan_crons = []
  for name, job in registered.items():
    if name not in expected_crons:
      if name.startswith("local-"):
        continue # local-* crons silently excluded
      if not any(name.startswith(p) for p in ["orch-", "agent-", "system-"]):
        continue
      orphan_crons.append(name)
  if orphan_crons:
    res.add(f"Orphan crons: {len(orphan_crons)}", "INFO",
        f"Not in expected list: {', '.join(orphan_crons[:5])}",
        "Rename to local-<name> to opt a cron out of doctor checks")
  else:
    res.add("Crons: orphans", "PASS", "no unexpected crons found")

  expected_set = set(expected_crons)
  extra = [str(n) for n in registered if n not in expected_set if not n.startswith("local-")]
  if extra:
    display = sorted(extra)
    if len(display) <= 5:
      for name in display:
        suggestion = find_similar_name(name, expected_set)
        status = "WARN" if suggestion else "INFO"
        detail = f"did you mean '{suggestion}'?" if suggestion else "not part of Hermes Cortex"
        res.add(f"Extra cron ({name})", status, detail)
    else:
      near_misses = [(n, find_similar_name(n, expected_set)) for n in display[:10]]
      warnings = [(n, s) for n, s in near_misses if s]
      for name, suggestion in warnings[:3]:
        res.add(f"Extra cron ({name})", "WARN", f"did you mean '{suggestion}'?")
      info_total = len(extra) - len(warnings)
      if info_total > 0:
        res.add("Extra crons", "INFO",
            f"{info_total} cron(s) not part of system — benign user/workday crons (e.g. {', '.join(display[:3])}...)")

  orch_crons_list = parse_orch_crons()
  is_orch = AGENT_ROLE == "orchestrator"
  _orch_hostname = run_bg(["hostname", "-s"]).strip() or "unknown"
  if orch_crons_list:
    missing_orch = [n for n in orch_crons_list if n not in registered]
    if is_orch and missing_orch:
      res.add("Orch crons missing", "FAIL",
          f"orchestrator host '{_orch_hostname}' missing {len(missing_orch)}: {', '.join(missing_orch)}",
          "Run: bash install-orch-crons.sh --force")
    elif is_orch and not missing_orch:
      res.add("Orch crons", "PASS",
          f"all {len(orch_crons_list)} orchestrator crons present (host: {_orch_hostname})")
    elif not is_orch and not missing_orch:
      res.add("Orch crons on non-orch", "WARN",
          f"{len(orch_crons_list)} orchestrator crons exist on non-orch host '{_orch_hostname}'",
          "Run: bash install-orch-crons.sh --uninstall")

  res.add("Crons total", "PASS" if len(registered) > 0 else "WARN", f"{len(registered)} jobs registered")


def check_scripts(res):
  """3. Script integrity: all scripts referenced by crons exist and match repo source."""
  if not JOBS_FILE.exists():
    return
  try:
    data = json.loads(JOBS_FILE.read_text())
  except (json.JSONDecodeError, OSError):
    return

  jobs = data.get("jobs", []) if isinstance(data, dict) else data
  script_dirs = [HERMES_HOME / "scripts", CORTEX_HOME / "scripts", HOME / ".local" / "bin"]
  repo_scripts = CORTEX_REPO / "ops" / "scripts"
  import hashlib as _hl
  missing = []
  mismatched = []

  for job in jobs:
    if not isinstance(job, dict):
      continue
    script = job.get("script", "")
    if not script:
      continue
    found = False
    for d in script_dirs:
      deployed = d / script
      if deployed.exists():
        found = True
        # ── Content verification: compare MD5 with repo source ──
        # Repo layout is NOT flat: scripts live under ops/scripts/<subdir>/
        # (health/, manage/, agent/, install/, bus/). Look up the real source
        # by basename, preferring the closest match. (Before 2026-08-02 this
        # used repo_scripts / script directly — a flat path — so scripts in
        # subdirectories silently skipped the MD5 check and stale deployed
        # copies passed. That let the stale Jul-31 watchdog with gbrain
        # checks survive a doctor PASS.)
        repo_source = repo_scripts / script
        if not repo_source.is_file():
          try:
            matches = sorted(repo_scripts.rglob(script))
            if matches:
              repo_source = matches[0]
          except OSError:
            pass
        if repo_source.is_file():
          try:
            # Strip SOURCE header from deployed copy (cortex-update.sh adds it;
            # since 2026-08-02 the header sits BELOW the shebang)
            _raw = deployed.read_bytes()
            _text = _raw.decode("utf-8", errors="surrogateescape")
            _lines = _text.splitlines(keepends=True)
            # New layout: shebang line 0, header lines 1-3 → keep shebang, drop header
            if len(_lines) >= 4 and _lines[0].startswith("#!") and _lines[1].startswith("# SOURCE:") and "Do NOT edit" in _lines[2]:
              _content = "".join([_lines[0]] + _lines[4:])
            # Legacy layout: header lines 0-2, content (incl. shebang) from line 3
            elif len(_lines) >= 3 and _lines[0].startswith("# SOURCE:") and "Do NOT edit" in _lines[1]:
              _content = "".join(_lines[3:])
            else:
              _content = _text
            dep_md5 = _hl.md5(_content.encode("utf-8", errors="surrogateescape")).hexdigest()
            src_md5 = _hl.md5(repo_source.read_bytes()).hexdigest()
            if dep_md5 != src_md5:
              mismatched.append((job.get("name", "?"), script, deployed))
          except (OSError, PermissionError):
            pass  # expected — silently handled
        break
    if not found and Path(script).is_absolute() and Path(script).exists():
      found = True
    if not found:
      missing.append((job.get("name", "?"), script))

  if not missing and not mismatched:
    res.add("Script integrity", "PASS", "all cron scripts found and match repo source")
  else:
    for name, script in missing[:5]:
      res.add(f"Script ({name})", "FAIL", f"not found: {script}",
          "Run: bash cortex-update.sh ")
    for name, script, deployed_path in mismatched[:5]:
      res.add(f"Script content ({name})", "FAIL",
          f"{script} — deployed copy differs from repo source",
          f"REQUIRED: Run: cortex-update.sh to resync")


def check_cron_runtime_scripts(res):
  """Cron runtime path integrity: ~/.hermes/scripts must resolve to the SAME
  tree as ~/.hermes-cortex/scripts (cortex-update deploy target).

  The cron scheduler resolves every no_agent job's script against
  HERMES_HOME/scripts (cron/scheduler.py enforces containment there). If
  that path is a SEPARATE real directory instead of a symlink (or an
  equivalent resolution), the scheduler executes stale deployed files and
  `check_deploy_checksums` still reports PASS (it only checks
  ~/.hermes-cortex/scripts). Detected 2026-08-02: watchdog ran a frozen
  Jul-31 copy with gbrain checks after the gbrain→mycortex migration.

  Expected end state (cortex-update.sh): ~/.hermes/scripts is a symlink to
  ~/.hermes-cortex/scripts, OR both resolve to the same directory.
  """
  runtime = HERMES_HOME / "scripts"
  deploy = CORTEX_HOME / "scripts"

  try:
    runtime_resolved = runtime.resolve()
    deploy_resolved = deploy.resolve()
  except OSError:
    res.add("Cron runtime scripts", "FAIL", "cannot resolve script dirs",
        "Check permissions on ~/.hermes and ~/.hermes-cortex")
    return

  if not runtime.exists():
    res.add("Cron runtime scripts", "FAIL",
        f"{runtime} missing — scheduler will fail every no_agent cron",
        "Run: bash cortex-update.sh (it creates the symlink)")
    return
  if not deploy.exists():
    res.add("Cron runtime scripts", "WARN",
        f"{deploy} missing — deploy target absent",
        "Run: bash cortex-update.sh")
    return

  if runtime_resolved == deploy_resolved:
    if runtime.is_symlink():
      res.add("Cron runtime scripts", "PASS",
          f"{runtime.name} → {str(deploy_resolved).replace(str(HOME), '~')} (symlink)")
    else:
      res.add("Cron runtime scripts", "PASS",
          "resolves to the same directory as deploy target")
    return

  # Divergent real directory — the stale-cron-copy failure mode
  res.add("Cron runtime scripts", "FAIL",
      f"{runtime} is a separate directory from {deploy} — cron scripts run STALE copies",
      "Remove unique files from ~/.hermes/scripts (back them up first), then run: bash cortex-update.sh to symlink")

def _check_bus_e2e(res):
  """End-to-end bus test: config → health → self round-trip → stuck msgs → EXEC path."""
  try:
    from hermes_paths import ensure_scripts_path
    ensure_scripts_path()
    from lib.cortex_bus import bus_send, bus_read, bus_archive, bus_health
  except ImportError:
    res.add("Bus E2E test", "SKIP",
        "cortex_bus.py not importable — expected if bus is not deployed on this agent")
    return

  agent = (os.environ.get("AGENT_NAME", "")
       or _read_config_from_bus_conf("AGENT_NAME")
       or os.environ.get("USER", "unknown"))
  queue = f"inbox_{agent}"

  # ── 1. Config check ──
  try:
    from lib.cortex_bus import BUS_URL, BUS_FALLBACK_URL
    bus_url = BUS_URL
    fallback_url = BUS_FALLBACK_URL
    if bus_url:
      res.add("Bus config (URL)", "PASS", f"BUS_URL set")
    else:
      res.add("Bus config (URL)", "FAIL", "BUS_URL not set", "Set CORTEX_BUS_URL in cortex-bus.conf")
    if fallback_url:
      res.add("Bus config (fallback)", "PASS", f"FALLBACK_URL set")
    else:
      res.add("Bus config (fallback)", "WARN", "No FALLBACK_URL configured",
          "Add CORTEX_BUS_FALLBACK_URL in cortex-bus.conf for resilience")
  except Exception:
    return # cortex_bus not importable — bus checks handled by earlier import guard

  # ── 2. Health check ──
  try:
    h = bus_health()
    status = h.get("status", "unknown")
    if status == "ok":
      res.add("Bus health", "PASS", f"Status: {status} — backend: {h.get('backend', '?')}")
    else:
      res.add("Bus health", "WARN", f"Status: {status}")
  except Exception as e:
    res.add("Bus health", "FAIL", str(e), "Check CORTEX_BUS_URL in cortex-bus.conf")
    return

  # ── 3. Self round-trip: send → read → archive ──
  test_cid = f"doctor-e2e-{os.urandom(4).hex()}"
  try:
    send_r = bus_send(queue, {
      "from": agent, "to": agent,
      "subject": "DOCTOR_TEST", "correlation_id": test_cid,
      "body": json.dumps({"test": True}),
    })
    if not send_r or not send_r.get("msg_id"):
      res.add("Bus self (send)", "FAIL", f"No msg_id returned: {send_r}",
          "Check auth credentials in cortex-bus.conf")
      return
  except Exception as e:
    res.add("Bus self (send)", "FAIL", str(e),
        "Check: curl -u user:pass CORTEX_BUS_URL/api/pgmq/send")
    return

  read_r = None
  for attempt in range(3):
    read_r = bus_read(queue, vt=30)
    if read_r and read_r.get("msg_id"):
      break
    time.sleep(0.5)

  if not read_r or not read_r.get("msg_id"):
    res.add("Bus self (read)", "FAIL", "No message read back after send",
        "Message may have been consumed by another process or VT expired")
    return

  body = read_r.get("body", {})
  if not isinstance(body, dict):
    body = {}

  cid = body.get("correlation_id", "")
  cid_ok = cid == test_cid
  arch_ok = bus_archive(queue, read_r["msg_id"])

  if cid_ok and arch_ok:
    res.add("Bus self (send→read→archive)", "PASS",
        f"correlation_id match — full cycle OK")
  elif arch_ok:
    res.add("Bus self (send→read→archive)", "PASS",
        f"read {cid or 'message'} instead of test — bus path OK")
  else:
    res.add("Bus self (archive)", "WARN",
        f"Sent and read OK but archiving failed", "Check PGMQ archive endpoint")
    return

  # ── 4. Stuck processing messages ──
  # Catches the exact symptom on Esther: handler reads but crashes before archive,
  # leaving messages stuck in 'processing' state that loop forever on VT expiry.
  # Query PGMQ API directly since health endpoint returns queue count, not per-queue details.
  try:
    import urllib.request
    from lib.cortex_bus import BUS_URL, CORTEX_BUS_TOKEN, CORTEX_BUS_AUTH
    bus_url = BUS_URL
    # Use Bearer if token available, otherwise Basic auth
    scheme, creds = "Bearer", CORTEX_BUS_TOKEN
    if not creds:
      import base64
      scheme, creds = "Basic", base64.b64encode(CORTEX_BUS_AUTH.encode()).decode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/queue/{queue}")
    if creds:
      req.add_header("Authorization", f"{scheme} {creds}")
    resp = urllib.request.urlopen(req, timeout=8)
    q_info = json.loads(resp.read().decode())
    # list_queues() returns {name, depth, processing, dlq, parent, created}
    pending_count = q_info.get("depth", 0)
    processing_count = q_info.get("processing", 0)
    if processing_count > 0:
      res.add("Bus stuck msgs", "FAIL",
          f"{processing_count} message(s) stuck in 'processing' state for {queue}",
          "Handler is crashing before archive — run: git pull && cortex-update.sh ")
    elif pending_count > 0:
      res.add("Bus stuck msgs", "WARN",
          f"{pending_count} pending message(s) in {queue} — may be normal",
          "Check if another agent is sending to your inbox")
    else:
      res.add("Bus stuck msgs", "PASS",
          "No stuck messages — queue empty and healthy")
  except Exception as e:
    res.add("Bus stuck msgs", "SKIP",
        f"Cannot query queue stats: {e}")

  # ── 5. Handler script check ──
  # Verify the handler script exists at the expected path (will be what processes EXEC)
  handler_path = CORTEX_HOME / "scripts" / "agent-message-handler.py"
  if handler_path.is_file():
    handler_size = os.path.getsize(handler_path)
    res.add("Bus handler", "PASS",
        f"agent-message-handler.py exists ({handler_size} bytes)")
  else:
    res.add("Bus handler", "FAIL",
        "agent-message-handler.py not found at expected path",
        f"Run: cortex-update.sh (expected at {handler_path})")


def _check_self_stale(res):
  """Check if the running doctor is stale vs the repo source."""
  try:
    # This script's deployed path vs repo source path
    deployed = Path(__file__).resolve()
    repo_source = CORTEX_REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "checks.py"

    if not repo_source.is_file():
      res.add("Doctor self", "SKIP", "Cannot find repo source to compare versions")
      return

    # Compare content hash — tolerate small mtime drift from deploy/copy latency
    import hashlib as _hl
    # Strip SOURCE header from deployed copy before hashing (cortex-update.sh
    # adds it; since 2026-08-02 the header sits BELOW the shebang)
    _raw = deployed.read_bytes()
    _text = _raw.decode("utf-8", errors="surrogateescape")
    _lines = _text.splitlines(keepends=True)
    # New layout: shebang line 0, header lines 1-3 → keep shebang, drop header
    if len(_lines) >= 4 and _lines[0].startswith("#!") and _lines[1].startswith("# SOURCE:") and "Do NOT edit" in _lines[2]:
      _content = "".join([_lines[0]] + _lines[4:])
    # Legacy layout: header lines 0-2, content (incl. shebang) from line 3
    elif len(_lines) >= 3 and _lines[0].startswith("# SOURCE:") and "Do NOT edit" in _lines[1]:
      _content = "".join(_lines[3:])
    else:
      _content = _text
    deployed_hash = _hl.md5(_content.encode("utf-8", errors="surrogateescape")).hexdigest()
    repo_hash = _hl.md5(repo_source.read_bytes()).hexdigest()

    if deployed_hash != repo_hash:
      res.add("Doctor version", "WARN",
          "Running older version — repo source differs",
          "Run: cortex-update.sh ")
    else:
      res.add("Doctor version", "PASS", "Deployed version matches repo")
  except Exception as e:
    res.add("Doctor self", "SKIP", f"Version check error: {e}")


def _check_required_tools(res):
  """Verify runtime tools exist on PATH. Prevents silent 'command not found'
  failures (the jq incident: contact-orchestrator.sh depended on jq, which was in no
  prereq list — hosts without it broke at runtime)."""
  import shutil
  tools = {
    "python3": "runtime scripts (contact-orchestrator.sh, handler, doctor)",
    "git": "repo pull/push, hooks",
    "curl": "bus HTTP client, doctor HTTP checks, health pings",
  }
  # jq is intentionally NOT required — scripts must use python3 for JSON.
  # bash >= 4 is checked by cortex-update.sh itself.
  for tool, used_by in tools.items():
    if shutil.which(tool):
      res.add(f"Tool ({tool})", "PASS", f"found — {used_by}")
    else:
      res.add(f"Tool ({tool})", "FAIL",
          f"missing — required for {used_by}",
          f"Install: {tool} via your package manager (see docs/setup-reference.md)")


def check_services(res):
  """4. Service health: external endpoints, Ollama, gbrain, bus, and self-version."""
  _check_self_stale(res)
  _check_required_tools(res)
  # External services are orchestrator-only (Dashboard, Langfuse, Agent Bus)
  if AGENT_ROLE == "orchestrator":
    for name, url, expected in EXTERNAL_SERVICES:
      try:
        code = http_get(url, timeout=8)
      except Exception as e:
        res.add(f"Service ({name})", "FAIL", f"Connection error: {e}", "Check nginx")
        continue
      if code == expected or code in ("200", "301", "302", "401"):
        res.add(f"Service ({name})", "PASS", f"HTTP {code}")
      elif code == "000":
        res.add(f"Service ({name})", "FAIL", "Connection refused", "Check nginx")
      else:
        res.add(f"Service ({name})", "WARN", f"HTTP {code} (unexpected)")

  # Agent Bus direct health
  if process_running("agent_bus"):
    bus_url = run_bg([CURL, "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://127.0.0.1:8903/health", "--max-time", "5"])
    if bus_url == "200":
      res.add("Agent Bus (direct)", "PASS",
          "HTTP 200 — bus service healthy via localhost:8903")
    elif bus_url == "000":
      res.add("Agent Bus (direct)", "FAIL",
          "agent-bus process running but port 8903 unreachable",
          "Check: systemctl --user status agent-bus")
    else:
      res.add("Agent Bus (direct)", "FAIL",
          f"HTTP {bus_url} — unexpected response",
          "Check: systemctl --user status agent_bus")
  else:
    def _get_conf(key):
      val = os.environ.get(key, "")
      if val:
        return val
      conf = CORTEX_HOME / "cortex-bus.conf"
      if conf.exists():
        for line in conf.read_text().splitlines():
          if line.startswith(f"{key}="):
            v = line.split("=", 1)[1].strip().strip("\"'")
            if v and "127.0.0.1" not in v:
              return v
      return ""
    bus_url = _get_conf("CORTEX_BUS_URL")
    bus_fallback = _get_conf("CORTEX_BUS_FALLBACK_URL")
    if bus_url or bus_fallback:
      parts = []
      if bus_url:
        parts.append("BUS_URL set")
      if bus_fallback:
        parts.append("FALLBACK_URL set")
      res.add("Agent Bus (direct)", "PASS",
          "Bus configured: " + " & ".join(parts))
    else:
      res.add("Agent Bus (direct)", "FAIL",
          "No bus URLs configured",
          "Set CORTEX_BUS_URL (and CORTEX_BUS_FALLBACK_URL) in cortex-bus.conf")

  _check_bus_e2e(res)

  # Non-orch guard: detect orchestrator-only services running on non-orch agents
  if AGENT_ROLE != "orchestrator":
    _bus_proc = run_bg(["pgrep", "-f", "agent_bus.server"], timeout=5) or ""
    if "agent_bus" in _bus_proc:
      res.add("Bus (non-orch guard)", "WARN",
          "agent_bus process running on non-orch agent — should only run on orchestrator hosts",
          "Stop: systemctl --user stop agent-bus && systemctl --user disable agent-bus")

  # Ollama
  out = run_bg([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
  if out:
    try:
      models = json.loads(out).get("models", [])
      if models:
        res.add("Ollama", "PASS", f"{len(models)} model(s) loaded")
      else:
        res.add("Ollama", "WARN", "Running but no models", "Run: ollama pull <model>")
    except json.JSONDecodeError:
      res.add("Ollama", "WARN", "Responding but not returning model list")
  else:
    res.add("Ollama", "FAIL", "Not reachable on localhost:11434",
        "Run: systemctl --user start ollama || ollama serve")

  # gbrain daemon — DECOMMISSIONED 2026-08-02 (owner-approved; mycortex replaces).
  # Expected states:
  #   - autopilot active          → PASS (pre-flip rollback state, or non-decommissioned host)
  #   - autopilot disabled/absent → PASS with note (decommissioned — intended)
  #   - autopilot enabled but inactive → WARN (half-decommissioned)
  _autopilot_enabled = False
  _autopilot_active = False
  if IS_MAC:
    out = run_bg(["launchctl", "list", "com.gbrain.autopilot"], timeout=5)
    _autopilot_active = '"PID"' in out
  else:
    out = run_bg(["systemctl", "--user", "is-active", "gbrain-autopilot"], timeout=5)
    _autopilot_active = out.strip() == "active"
    out2 = run_bg(["systemctl", "--user", "is-enabled", "gbrain-autopilot"], timeout=5)
    _autopilot_enabled = out2.strip() == "enabled"
  if _autopilot_active:
    res.add("gbrain daemon", "PASS", "autopilot active (rollback state — decommission pending on this host)")
  elif _autopilot_enabled:
    res.add("gbrain daemon", "WARN", "autopilot enabled but inactive",
        "Run: systemctl --user disable gbrain-autopilot (decommission) or start it (rollback)")
  else:
    res.add("gbrain daemon", "PASS", "decommissioned (autopilot disabled; mycortex is the knowledge brain)")

  # Worker service conflict check
  if IS_LINUX:
    worker_active = run_bg(["systemctl", "--user", "is-active", "hermes-agent-worker"], timeout=5).strip()
    if worker_active == "active":
      handler_cron_active = run_bg(["crontab", "-l"], timeout=5)
      has_handler = "agent-message-handler" in handler_cron_active
      if has_handler:
        res.add("worker-service", "WARN",
            "hermes-agent-worker active + agent-message-handler cron — "
            "worker consumes inbox messages with vt=120 and skips non-workflow types, "
            "preventing the handler from seeing them",
            "Stop/disable: systemctl --user stop hermes-agent-worker && "
            "systemctl --user disable hermes-agent-worker && "
            "rm ~/.config/systemd/user/hermes-agent-worker.service && "
            "systemctl --user daemon-reload")
      else:
        res.add("worker-service", "PASS",
            "hermes-agent-worker active (no handler cron — no conflict)")
    elif worker_active == "inactive" or "inactive" in worker_active:
      res.add("worker-service", "PASS", "hermes-agent-worker not active")
    elif worker_active:
      res.add("worker-service", "WARN",
          f"hermes-agent-worker state: {worker_active}",
          "systemctl --user status hermes-agent-worker")


def check_system(res):
  """5. System resources: disk, memory, systemd service scope."""
  if IS_LINUX:
    out = run_bg(["sh", "-c", "ls /etc/systemd/system/hermes-*.service 2>/dev/null"], timeout=5)
    if out.strip():
      count = len(out.strip().split("\n"))
      res.add("Systemd scope", "WARN",
          f"{count} Hermes service(s) found in /etc/systemd/system/ (must use ~/.config/systemd/user/)",
          "sudo systemctl disable --now hermes-dashboard hermes-health hermes-gateway ; "
          "sudo rm /etc/systemd/system/hermes-*.service ; "
          "sudo rm /etc/systemd/system/multi-user.target.wants/hermes-*.service ; "
          "sudo systemctl daemon-reload")
    else:
      res.add("Systemd scope", "PASS", "no system-level Hermes services (all user-level)")

  out = run_bg(["df", "-h", "/"], timeout=5)
  if out:
    lines = out.strip().split("\n")
    if len(lines) >= 2:
      parts = lines[-1].split()
      if len(parts) >= 5:
        used = parts[2]
        avail = parts[3]
        pct = parts[4].rstrip("%")
        try:
          pct_int = int(pct)
          if pct_int < 80:
            status = "PASS"
            fix = ""
          elif pct_int < 90:
            status = "WARN"
            fix = "Free space: sudo journalctl --vacuum-size=500M; sudo apt autoremove"
          else:
            status = "FAIL"
            fix = "Free space: sudo journalctl --vacuum-size=500M; sudo apt autoremove"
          res.add("Disk usage", status, f"{used} used / {avail} free ({pct}%)", fix)
        except ValueError:
          print("expected — silently handled", file=sys.stderr)

  if IS_MAC:
    total_mem = run_bg(["sysctl", "-n", "hw.memsize"], timeout=5)
    if total_mem.isdigit():
      total_gb = int(total_mem) / 1073741824
      vm_out = run_bg(["vm_stat"], timeout=5)
      pages_free = pages_spec = pages_purge = 0
      for line in vm_out.split("\n"):
        m = re.search(r"Pages free:\s+(\d+)", line)
        if m:
          pages_free = int(m.group(1))
        m = re.search(r"Pages speculative:\s+(\d+)", line)
        if m:
          pages_spec = int(m.group(1))
        m = re.search(r"Pages purgable:\s+(\d+)", line)
        if m:
          pages_purge = int(m.group(1))
      total_pages = int(total_mem) / 16384
      used_pages = total_pages - pages_free - pages_spec - pages_purge
      used_gb = used_pages * 16384 / 1073741824
      res.add("Memory", "PASS", f"{used_gb:.1f}G used / {total_gb:.0f}G total")
  else:
    out = run_bg(["free", "-h"])
    if out:
      for line in out.split("\n"):
        if line.startswith("Mem:"):
          parts = line.split()
          if len(parts) >= 3:
            res.add("Memory", "PASS", f"{parts[2]} used / {parts[1]} total")
          break

  if IS_LINUX:
    ss_out = run_bg(["ss", "-tlnp"], timeout=5)
    if ss_out:
      exposed = []
      for line in ss_out.splitlines():
        if "0.0.0.0:11434" in line and "ollama" in line.lower():
          exposed.append("Ollama on 0.0.0.0:11434")
        elif "0.0.0.0:8903" in line:
          exposed.append("Agent Bus on 0.0.0.0:8903")
        elif "0.0.0.0:4000" in line and "langfuse" in line.lower():
          exposed.append("Langfuse on 0.0.0.0:4000")
      if exposed:
        for e in exposed:
          res.add("Network safety", "WARN",
              f"{e} — exposed to all network interfaces",
              "Configure nginx to proxy and bind service to 127.0.0.1 only")
      else:
        res.add("Network safety", "PASS", "no services exposed on 0.0.0.0")

  if IS_LINUX:
    linger_out = run_bg(["loginctl", "show-user", os.environ.get("USER", "moses")], timeout=5)
    if "Linger=yes" in linger_out or "Linger=on" in linger_out:
      res.add("Systemd linger", "PASS", "enabled — user services survive reboot")
    else:
      res.add("Systemd linger", "WARN",
          "NOT enabled — user services die on logout/reboot",
          "Run: sudo loginctl enable-linger $(whoami)")

  # ── Stale systemd units check ──
  # Catches duplicate/stale .service files still enabled and hitting restart limits.
  # The expected active services below are the canonical Cortex user services.
  # Units that are DISABLED (intentionally stopped — e.g. decommissioned
  # gbrain-autopilot/gbrain-sync) are skipped: a disabled unit in failed
  # state is the intended post-decommission state, not an operational issue.
  expected_user_units = {
    "hermes-cortex-dashboard.service",
    "hermes-cortex-langfuse.service",
    "hermes-cortex-agent-bus.service",
  }
  if IS_LINUX:
    failed = run_bg(["systemctl", "--user", "list-units", "--state=failed",
             "--no-legend", "--no-pager"], timeout=5)
    stale = []
    if failed and failed.strip():
      for line in failed.strip().split("\n"):
        parts = line.split()
        if len(parts) < 3:
          continue
        # Format: [bullet] UNIT LOAD ACTIVE SUB DESCRIPTION
        # bullet column only present for failed/masked units
        offset = 1 if parts[0] == "●" else 0
        unit = parts[offset]
        load_state = parts[offset + 1] if len(parts) > offset + 1 else ""
        # Skip masked units (system portal services on headless servers)
        if load_state == "masked":
          continue
        if unit not in expected_user_units:
          # Skip DISABLED units — intentionally stopped (decommissioned)
          en = run_bg(["systemctl", "--user", "is-enabled", unit], timeout=5)
          if en.strip() == "disabled":
            continue
          stale.append(unit)
    if stale:
      names = ", ".join(stale)
      res.add("Systemd stale units", "FAIL",
          f"{len(stale)} stale/failed unit(s): {names}",
          "systemctl --user disable --now <unit> && "
          "rm ~/.config/systemd/user/<unit> && "
          "systemctl --user daemon-reload")
    else:
      res.add("Systemd stale units", "PASS", "no unexpected failed units")


def check_config(res):
  """6. Config consistency: hermes-cortex.env var cross-reference."""
  env_path = CORTEX_ENV if CORTEX_ENV.exists() else LEGACY_MODELS_ENV
  if not env_path.exists():
    res.add("Config (hermes-cortex.env)", "WARN", "Not found",
        "Create ~/hermes-cortex/.env with env vars")
    return

  text = env_path.read_text()
  defined = {}
  for line in text.split("\n"):
    line = line.strip()
    if not line or line.startswith("#"):
      continue
    m = re.match(r"^(?:export\s+)?(\w+)=(.*)", line)
    if m:
      defined[m.group(1)] = line

  if not defined:
    res.add("Config (hermes-cortex.env)", "WARN", "File exists but no exports defined",
        "Add JUDGE_MODEL, EMBEDDING_MODEL etc.")
    return

  consumers_by_var = find_script_consumers()
  for var, consumer_names in consumers_by_var.items():
    if var not in defined:
      res.add(f"Config ({var})", "WARN", f"Not defined in hermes-cortex.env",
          f"Add: export {var}=<model-name> to ~/hermes-cortex/.env")
    else:
      if consumer_names:
        res.add(f"Config ({var})", "PASS", f"defined, {len(consumer_names)} consumer(s) found")
      else:
        res.add(f"Config ({var})", "INFO", f"defined but zero consumer scripts reference it")


def check_nginx(res):
  """7. Nginx config: file exists, htpasswd, agent-card, SSL certs, syntax."""

  def _path_ok(p):
    try:
      return Path(p).exists()
    except PermissionError:
      return True

  def _path_info(p):
    try:
      p_obj = Path(p)
      if p_obj.exists():
        return "exists"
      return "missing"
    except PermissionError:
      return "exists (root-owned, not readable by this user)"

  nginx_brew_dir = None
  config_dir = None
  available_dir = None
  htpasswd_expected = None

  if IS_MAC:
    if os.uname().machine == "arm64":
      nginx_brew_dir = Path("/opt/homebrew/etc/nginx")
    else:
      nginx_brew_dir = Path("/usr/local/etc/nginx")
    config_dir = nginx_brew_dir / "servers"
    available_dir = config_dir
    htpasswd_expected = nginx_brew_dir / ".htpasswd"
  elif IS_LINUX:
    nginx_brew_dir = Path("/etc/nginx")
    config_dir = nginx_brew_dir / "sites-enabled"
    available_dir = nginx_brew_dir / "sites-available"
    htpasswd_expected = nginx_brew_dir / ".hermes-htpasswd"
  else:
    res.add("Nginx config", "INFO", "Unsupported OS — skipping nginx checks")
    return

  if not nginx_brew_dir or not nginx_brew_dir.is_dir():
    res.add("Nginx config", "INFO", "nginx not installed — skipping checks")
    return

  conf_available = available_dir / "hermes-services.conf"
  if not conf_available.is_file():
    res.add("Nginx config", "FAIL", f"not found at {conf_available}",
        "Run: sudo ops/install/deploy/nginx/install-nginx-full.sh")
    return
  res.add("Nginx config", "PASS", f"found at {conf_available}")

  text = conf_available.read_text()

  placeholders = [
    "__HTPASSWD_FILE__", "__NGINX_CONFIG_DIR__", "__NGINX_LOG_DIR__",
    "__CORTEX_HOME__", "__SSL_CERT__", "__SSL_CERT_KEY__",
  ]
  found_placeholders = [p for p in placeholders if p in text]
  if found_placeholders:
    res.add("Nginx placeholders", "FAIL",
        f"unsubstituted: {', '.join(found_placeholders)}",
        "Run: cortex-update.sh or hermes-services-apply.py")

  htpasswd_path = None
  for line in text.split("\n"):
    m = re.search(r"auth_basic_user_file\s+(\S+?);?\s*$", line)
    if m:
      htpasswd_path = m.group(1).rstrip(";")
      break

  if htpasswd_path:
    p = Path(htpasswd_path)
    if _path_ok(htpasswd_path):
      res.add("Nginx htpasswd", "PASS", f"{htpasswd_path} {_path_info(htpasswd_path)}")
    elif _path_ok(str(htpasswd_expected)):
      res.add("Nginx htpasswd", "FAIL",
          f"config points to '{htpasswd_path}' (not found) — expected '{htpasswd_expected}'",
          f"Re-deploy: cortex-update.sh ")
    else:
      res.add("Nginx htpasswd", "FAIL",
          f"not found at '{htpasswd_path}' (and expected '{htpasswd_expected}' also missing)",
          "Run: sudo htpasswd -c /etc/nginx/.hermes-htpasswd <user>")
  else:
    res.add("Nginx htpasswd", "INFO", "no auth_basic_user_file in config")

  seen_cards = set()
  agent_card_found = 0
  agent_card_missing = 0
  for line in text.split("\n"):
    m = re.search(r"alias\s+(\S+?/agent-card\.json)", line)
    if m:
      card_path = m.group(1).rstrip(";")
      if card_path in seen_cards:
        continue
      seen_cards.add(card_path)
      if _path_ok(card_path):
        agent_card_found += 1
      else:
        agent_card_missing += 1
        res.add("Nginx agent-card", "FAIL",
            f"not found at '{card_path}'",
            "Run: cortex-update.sh  OR generate agent card in that directory")

  if agent_card_found > 0 and agent_card_missing == 0:
    res.add("Nginx agent-card", "PASS", f"{agent_card_found} agent card alias(es) resolve")

  seen_certs = set()
  cert_found = 0
  cert_missing = 0
  for line in text.split("\n"):
    m = re.search(r"ssl_certificate(?:_key)?\s+(\S+?);?\s*$", line)
    if m:
      raw = m.group(1).rstrip(";")
      if raw in seen_certs or "__SSL_CERT" in raw:
        continue
      seen_certs.add(raw)
      if _path_ok(raw):
        cert_found += 1
      else:
        cert_missing += 1
        label = "SSL cert" if "key" not in m.group(0) else "SSL key"
        res.add(f"Nginx {label}", "FAIL",
            f"not found at '{raw}'",
            "Renew cert: sudo certbot renew OR set CORTEX_SSL_CERT_PATH env var")

  if "__SSL_CERT__" not in text and cert_found > 0 and cert_missing == 0:
    res.add("Nginx SSL certs", "PASS", f"{len(seen_certs)} cert path(s) resolve")

  # nginx -t syntax check
  if nginx_available():
    if os.geteuid() == 0:
      out, code = run(["nginx", "-t"], timeout=10)
    elif run(["which", "sudo"], timeout=5)[0]:
      r = subprocess.run(
        ["sudo", "nginx", "-t"], capture_output=True, text=True, timeout=15
      )
      out, code = r.stdout.strip(), r.returncode
      if code != 0 and (
        "a terminal is required" in r.stderr.lower()
        or "a terminal is required" in r.stdout.lower()
      ):
        out, code = run(["nginx", "-t"], timeout=10)
    else:
      res.add("Nginx syntax", "INFO", "not root and no sudo — skipping syntax check")
      return
    if code == 0:
      res.add("Nginx syntax", "PASS", "config valid (nginx -t)")
    else:
      lines = [
        l for l in out.split("\n")
        if "test failed" in l.lower() or "error" in l.lower()
      ][:3]
      detail = "; ".join(lines) if lines else "syntax error"
      res.add("Nginx syntax", "FAIL", detail, "Check: sudo nginx -t")


def nginx_available():
  """Check if nginx binary is on PATH."""
  out, _ = run(["which", "nginx"], timeout=5)
  return bool(out.strip())


def _check_enforcer_permissions(res, plugin_dir, hooks_dir):
  """Check that enforcement files have expected restrictive permissions."""
  checks = [
    ("Plugin __init__.py", plugin_dir / "__init__.py", 0o444),
    ("Pre-commit hook script", hooks_dir / "pre-commit", 0o555),
    ("Pre-push hook script", hooks_dir / "pre-push", 0o555),
    ("Post-commit hook script", hooks_dir / "post-commit", 0o555),
  ]
  for label, path, want in checks:
    if not path.exists() or path.is_symlink():
      continue # symlinks have different perms — skip
    try:
      have = path.stat().st_mode & 0o777
      if have == want:
        res.add(f"Perms: {label}", "PASS", f"{oct(want)}")
      else:
        # Check if file has chattr +i — if immutable, permissions
        # are irrelevant (chattr +i is stronger than 0o444 alone)
        is_immutable = False
        try:
          r = subprocess.run(
            ["lsattr", str(path)],
            capture_output=True, text=True, timeout=5,
          )
          if r.returncode == 0:
            flags = r.stdout.split()[0] if r.stdout else ""
            is_immutable = "i" in flags
        except (subprocess.TimeoutExpired, OSError, IndexError):
          pass  # expected — silently handled
        if is_immutable:
          res.add(f"Perms: {label}", "PASS",
              f"{oct(have)} (+ chattr +i) — immutable trumps")
        else:
          res.add(f"Perms: {label}", "WARN",
              f"expected {oct(want)}, got {oct(have)}",
              f"Fix: chmod {oct(want)[2:]} {path}")
    except OSError:
      continue # file removed between stat and read — skip gracefully


def _check_enforcer_immutability(res, plugin_dir, hooks_dir):
  """Check that critical enforcement files have the immutable (chattr +i) flag."""
  targets = [
    plugin_dir / "__init__.py",
    hooks_dir / "pre-commit",
    hooks_dir / "pre-push",
    hooks_dir / "post-commit",
    hooks_dir / "post-push",
    hooks_dir / "post-merge",
    CORTEX_HOME / "tools/loop-governance/loop-gov-mcp.py",
    CORTEX_HOME / "scripts/hermes-plugin-lock",
  ]
  # P1-A hardening (2026-07-31): the hooks DIRECTORY itself must be immutable
  # (symlink-swap guard — hooks/pre-commit is a symlink; without dir +i an
  # attacker can rm the symlink and re-point it at an arbitrary script).
  targets.append(hooks_dir)
  for path in targets:
    if not path.exists():
      continue
    # Resolve symlinks — the immutable flag is on the target file
    real_path = path.resolve() if path.is_symlink() else path
    try:
      result = subprocess.run(
        ["lsattr", str(real_path)],
        capture_output=True, text=True, timeout=5,
      )
      if result.returncode != 0:
        continue
      flags = result.stdout.split()[0] if result.stdout else ""
      if "i" in flags:
        res.add(f"Immutable: {path.name}", "PASS", "chattr +i set")
      else:
        res.add(f"Immutable: {path.name}", "FAIL",
            "immutable flag not set — enforcement file is modifiable",
            f"Fix: sudo hermes-plugin-lock lock")
    except (subprocess.TimeoutExpired, OSError, IndexError):
      continue # lsattr failed — skip gracefully


def _check_plugin_lock_helper(res):
  """Check that the plugin lock helper (hermes-plugin-lock) is deployed and functional.
  Linux:  /usr/local/sbin/hermes-plugin-lock + sudo -n (needs sudoers entry)
  macOS:  /usr/local/bin/hermes-plugin-lock  + direct run (chflags uchg, no root)
  """
  import platform as _platform
  _is_macos = _platform.system() == "Darwin"
  helper_path = Path("/usr/local/sbin/hermes-plugin-lock")
  deploy_path = "/usr/local/sbin"
  if _is_macos:
    helper_path = Path("/usr/local/bin/hermes-plugin-lock")
    deploy_path = "/usr/local/bin"

  # ── Helper binary exists and is executable ──
  if not helper_path.exists():
    res.add("Plugin lock helper", "FAIL",
        f"hermes-plugin-lock not found at {helper_path}",
        f"Run: cortex-update.sh (deploys to {deploy_path}/)")
    return
  if not os.access(str(helper_path), os.X_OK):
    res.add("Plugin lock helper", "FAIL",
        f"{helper_path} exists but is not executable",
        f"Fix: sudo chmod 755 {helper_path}")
    return

  # ── Functional test ──
  # Linux: sudo -n hermes-plugin-lock status (proves sudoers entry + helper)
  # macOS: hermes-plugin-lock status      (chflags uchg, no root needed)
  try:
    cmd = ["sudo", "-n", str(helper_path), "status"]
    if _is_macos:
      cmd = [str(helper_path), "status"]
    result = subprocess.run(
      cmd, capture_output=True, text=True, timeout=5,
    )
    if result.returncode == 0:
      res.add("Plugin lock helper", "PASS",
          f"helper OK ({result.stdout.strip()[:60]})")
    else:
      fix = f"Deploy helper via cortex-update.sh"
      if not _is_macos:
        fix = ("Add sudoers entry: echo '$(whoami) ALL=(root) NOPASSWD: "
            f"{helper_path}' | sudo tee /etc/sudoers.d/hermes")
      res.add("Plugin lock helper", "FAIL",
          f"hermes-plugin-lock status exited {result.returncode}: {result.stderr.strip()[:60]}",
          fix)
  except (subprocess.TimeoutExpired, OSError) as e:
    res.add("Plugin lock helper", "FAIL",
        f"hermes-plugin-lock status failed: {e}",
        "Check helper binary and deploy via cortex-update.sh")


def check_governance(res):
  """7. Governance system: plugin, pre-commit hook, MCP servers, lock files, score-cycle."""
  config_text = read_file(CONFIG_FILE)
  state_dir = CORTEX_HOME / "state"
  hooks_dir = CORTEX_HOME / "hooks"
  global_hooks_path = run_bg(["git", "config", "--global", "core.hooksPath"], timeout=5)

  # ── Governance plugin ──
  plugin_dir = HERMES_HOME / "plugins" / "governance-enforcer"
  plugin_src = CORTEX_REPO / "plugins" / "governance-enforcer"
  plugin_enabled = "governance-enforcer" in config_text and "enabled" in config_text

  if plugin_dir.exists() and (plugin_dir / "__init__.py").exists():
    res.add("Governance plugin", "PASS", "installed at ~/.hermes/plugins/governance-enforcer")
    if plugin_dir.is_symlink():
      target = os.readlink(str(plugin_dir))
      if plugin_src.exists() and str(plugin_src) in target:
        res.add("Plugin symlink", "FAIL",
            f"symlinked to {target} — should be a copy for chattr +i safety",
            "Run: cortex-update.sh (converts symlink→copy automatically)")
        # Check for stale __pycache__ — source .py newer than .pyc
        pycache_dir = plugin_src / "__pycache__"
        if pycache_dir.exists():
          stale_count = 0
          for pyc in pycache_dir.glob("*.pyc"):
            py_name = pyc.name.rsplit(".", 2)[0] + ".py"
            py_source = plugin_src / py_name
            if py_source.exists() and pyc.stat().st_mtime < py_source.stat().st_mtime:
              stale_count += 1
          if stale_count:
            res.add("Plugin pycache", "FAIL",
                f"{stale_count} stale .pyc file(s) — source is newer than compiled cache",
                f"REQUIRED: rm -rf {pycache_dir} && /reset (new session)")
          else:
            res.add("Plugin pycache", "PASS", "no stale .pyc files")
      else:
        res.add("Plugin symlink", "WARN",
            f"symlinked to {target} (not ~/hermes-cortex/.hermes-cortex/...)",
            "Re-create: ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/")
    else:
      deployed_init = plugin_dir / "__init__.py"
      repo_init = plugin_src / "__init__.py"
      if deployed_init.exists() and repo_init.exists():
        deployed_hash = hashlib.sha256(deployed_init.read_bytes()).hexdigest()
        repo_hash = hashlib.sha256(repo_init.read_bytes()).hexdigest()
        if deployed_hash == repo_hash:
          res.add("Plugin content", "PASS", "copy matches repo source")
        else:
          res.add("Plugin content", "FAIL",
              "deployed copy differs from repo — stale after git update",
              "REQUIRED: bash ~/hermes-cortex/ops/scripts/cortex-update.sh"
              " (sanctioned deploy path — deploys, relocks, and verifies)")
      else:
        res.add("Plugin content", "WARN",
            "can't compare — source or deployed __init__.py missing")
    # Verify enforcer has survey-before-cron gate (structural feature check)
    try:
      enforcer_init = (plugin_src / "__init__.py").read_text()
      if "SURVEY_MARKER" in enforcer_init:
        res.add("Enforcer survey gate", "PASS", "cronjob(create) requires .cron-survey-done marker")
      else:
        res.add("Enforcer survey gate", "WARN",
            "missing SURVEY_MARKER constant — survey-before-cron gate not active",
            "Pull latest hermes-cortex and run cortex-update.sh ")
    except (OSError, PermissionError):
      pass # plugin source not readable — skip survey gate check
  else:
    res.add("Governance plugin", "FAIL", "not installed",
        "Install: ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/\n"
        "Then: hermes plugins enable governance-enforcer --allow-tool-override\n"
        "Then: /reset (new session)")

  if plugin_enabled:
    res.add("Plugin config", "PASS", "enabled in config.yaml")
  else:
    res.add("Plugin config", "FAIL" if plugin_dir.exists() else "WARN",
        "not enabled in config.yaml",
        "Run: hermes plugins enable governance-enforcer --allow-tool-override")

  if plugin_src.exists() and (plugin_src / "__init__.py").exists():
    res.add("Plugin source", "PASS", "source in repo at plugins/governance-enforcer")
  else:
    res.add("Plugin source", "FAIL", "source missing in repo",
        "Check: ~/hermes-cortex/plugins/governance-enforcer/")

  # ── MCP servers ──
  is_orch = AGENT_ROLE == "orchestrator"
  for name, server_script in EXPECTED_MCP_SERVERS.items():
    # Orchestrator-only MCP servers (register_orch in cortex-update.sh) are
    # expected only on orchestrator hosts. On other hosts, absence is correct
    # and presence is drift worth a warning, not a failure.
    if name in ORCH_ONLY_MCP_SERVERS and not is_orch:
      if name in config_text:
        res.add(f"MCP server ({name})", "WARN",
            f"configured on non-orchestrator host — {name} is orchestrator-only",
            f"Remove the {name} mcp_servers entry from ~/.hermes/config.yaml")
      else:
        res.add(f"MCP server ({name})", "PASS",
            "not configured (correct for non-orchestrator)")
      continue

    if name not in config_text:
      res.add(f"MCP server ({name})", "FAIL", "not configured",
          f"Run: hermes mcp add {name} --command ~/.hermes/hermes-agent/venv/bin/python3 "
          f"--args ~/hermes-cortex/mcp-servers/{server_script}")
      continue

    res.add(f"MCP server ({name})", "PASS", "configured in config.yaml")

    if name == "loop-governance":
      cmd_match = re.search(
        rf"{re.escape(name)}.*?command:\s*(\S+)",
        config_text, re.DOTALL,
      )
      if cmd_match:
        cmd = cmd_match.group(1)
        if "venv" in cmd and "python3" in cmd:
          res.add(f"MCP Python ({name})", "PASS", f"uses venv: {cmd}")
        elif "python3" in cmd:
          venv_python = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python3"
          if venv_python.exists():
            res.add(f"MCP Python ({name})", "WARN",
                f"uses bare python3 (expected venv)",
                f"Run: hermes mcp update {name} --command {venv_python}")
          else:
            res.add(f"MCP Python ({name})", "WARN",
                f"uses python3 but venv not found at {venv_python}")

  # ── Pre-commit hook ──
  expected_hook_path = hooks_dir / "pre-commit"
  expected_hooks_path = str(hooks_dir)

  if global_hooks_path.rstrip("/") == expected_hooks_path:
    res.add("Global hooksPath", "PASS", f"core.hooksPath → {expected_hooks_path}")
  elif global_hooks_path:
    res.add("Global hooksPath", "WARN",
        f"set to '{global_hooks_path}' (expected '{expected_hooks_path}')",
        f"Run: git config --global core.hooksPath {expected_hooks_path}")
  else:
    res.add("Global hooksPath", "FAIL", "not set",
        f"Run: git config --global core.hooksPath {expected_hooks_path}")

  if expected_hook_path.exists():
    content = expected_hook_path.read_text()
    has_enforcer_check = "governance-enforcer/__init__.py" in content
    if has_enforcer_check and "score-cycle" in content and "governance" in content:
      res.add("Pre-commit hook", "PASS", "installed governance + enforcer checks")
    elif "score-cycle" in content and "governance" in content:
      res.add("Pre-commit hook", "WARN",
          "missing enforcer plugin presence check",
          "Update: bash ~/hermes-cortex/ops/scripts/cortex-update.sh"
          " (current hook is missing enforcer verification)")
    else:
      res.add("Pre-commit hook", "WARN", "installed but may be outdated",
          "Run: bash ~/hermes-cortex/ops/scripts/cortex-update.sh")
  else:
    res.add("Pre-commit hook", "FAIL", f"not found at {expected_hook_path}",
        "Install: bash ~/hermes-cortex/ops/scripts/cortex-update.sh\n"
        "The sanctioned deploy path installs and locks all hooks.")

  # ── Pre-push hook ──
  expected_push_hook = hooks_dir / "pre-push"
  if expected_push_hook.exists():
    push_content = expected_push_hook.read_text()
    if "pre-push-pull" in push_content:
      features = []
      features.append("lock-check")
      if "Changed-files syntax check" in push_content:
        features.append("syntax-check")
      res.add("Pre-push hook", "PASS", f"installed with {', '.join(features)}")
    else:
      res.add("Pre-push hook", "WARN", "installed but may be outdated")
  else:
    res.add("Pre-push hook", "WARN", "not installed",
        "Install: cp ~/hermes-cortex/ops/scripts/pre-push-pull ~/.hermes-cortex/hooks/pre-push\n"
        "Then: chmod +x ~/.hermes-cortex/hooks/pre-push")

  # ── Post-commit hook ──
  expected_post_commit = hooks_dir / "post-commit"
  expected_post_commit_src = CORTEX_HOME / "scripts" / "post-commit-audit"
  if not expected_post_commit.exists():
    res.add("Post-commit hook", "FAIL", "not installed",
        "Install: ln -sf ~/.hermes-cortex/scripts/post-commit-audit ~/.hermes-cortex/hooks/post-commit")
  elif expected_post_commit.is_symlink():
    target = expected_post_commit.resolve()
    if str(target) == str(expected_post_commit_src):
      if os.access(str(expected_post_commit), os.X_OK):
        res.add("Post-commit hook", "PASS",
            f"symlinked to post-commit-audit (executable)")
      else:
        res.add("Post-commit hook", "FAIL",
            "symlink target not executable",
            "Run: chmod +x ~/.hermes-cortex/scripts/post-commit-audit")
    else:
      res.add("Post-commit hook", "WARN",
          f"symlinks to {target} (expected {expected_post_commit_src})",
          f"Fix: ln -sf ~/.hermes-cortex/scripts/post-commit-audit ~/.hermes-cortex/hooks/post-commit")
  else:
    content = expected_post_commit.read_text()
    if "post-commit-audit" in content:
      res.add("Post-commit hook", "WARN",
          "is a file copy (expected symlink to post-commit-audit)")
    else:
      res.add("Post-commit hook", "WARN",
          "unknown content — expected post-commit-audit",
          "Install: ln -sf ~/.hermes-cortex/scripts/post-commit-audit ~/.hermes-cortex/hooks/post-commit")

  # ── Score-cycle CLI (old system) ──
  score_paths = [
    HOME / ".local" / "bin" / "score-cycle",
    Path("/usr/local/bin/score-cycle"),
    CORTEX_HOME / "scripts" / "score-cycle",
  ]
  found_score = None
  for p in score_paths:
    if p.exists():
      found_score = p
      break
  if found_score:
    res.add("Score-cycle", "INFO",
        f"Old score-cycle found at {found_score} — current governance uses MCP tools")
  else:
    res.add("Score-cycle", "OK",
        "Legacy score-cycle not present — MCP-based governance in use")

  # ── Stale governance locks ──
  # Uses heartbeat_at + ttl_seconds from the lock file.
  # A lock with a recent heartbeat (within TTL) is actively held — not stale.
  # Falls back to started_at > 24h for old locks without heartbeat_at.
  if not state_dir.exists():
    res.add("State directory", "INFO", "does not exist (will be created on first begin_change)")
  else:
    lock_files = list(state_dir.glob(".governance-*.json"))
    if lock_files:
      stale_count = 0
      active_count = 0
      now = time.time()
      for lf in lock_files:
        try:
          lock_data = json.loads(lf.read_text())
          # Primary check: heartbeat + TTL
          heartbeat_str = lock_data.get("heartbeat_at", "")
          ttl = lock_data.get("ttl_seconds", 3600)
          if heartbeat_str:
            try:
              hb_clean = heartbeat_str.replace("Z", "+00:00")
              hb_ts = datetime.fromisoformat(hb_clean).timestamp()
              elapsed = now - hb_ts
              if elapsed > ttl:
                stale_count += 1
                res.add(f"Stale lock ({lf.name})", "WARN",
                    f"heartbeat expired {elapsed:.0f}s ago (TTL: {ttl}s)",
                    f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
              else:
                active_count += 1
            except (ValueError, TypeError):
              stale_count += 1
              res.add(f"Stale lock ({lf.name})", "WARN",
                  f"unparseable heartbeat: {heartbeat_str}",
                  f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
          else:
            # Fallback: no heartbeat — use started_at > 24h heuristic
            started = lock_data.get("started_at", "")
            if started:
              try:
                started_ts = datetime.fromisoformat(started).timestamp()
                age_hours = (now - started_ts) / 3600
                if age_hours > 24:
                  stale_count += 1
                  res.add(f"Stale lock ({lf.name})", "WARN",
                      f"from {started} ({age_hours:.0f}h old, no heartbeat)",
                      f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
                else:
                  active_count += 1
              except (ValueError, TypeError):
                stale_count += 1
                res.add(f"Stale lock ({lf.name})", "WARN",
                    f"unparseable timestamp: {started}",
                    f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
            else:
              stale_count += 1
              res.add(f"Stale lock ({lf.name})", "WARN",
                  "no heartbeat or started_at field",
                  f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
        except (json.JSONDecodeError, OSError):
          stale_count += 1
          res.add(f"Stale lock ({lf.name})", "WARN",
              "unparseable lock file",
              f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")

      if stale_count == 0:
        if active_count > 0:
          res.add("Governance locks", "PASS",
              f"{active_count} lock(s) active, 0 stale")
        else:
          res.add("Governance locks", "PASS",
              f"{len(lock_files)} lock(s), none stale")
    else:
      res.add("Governance locks", "PASS", "no lock files")

  # ── Permission checks on enforcement files ──
  _check_enforcer_permissions(res, plugin_dir, hooks_dir)

  # ── Immutability (chattr +i) checks ──
  _check_enforcer_immutability(res, plugin_dir, hooks_dir)

  # ── Plugin lock helper (hermes-plugin-lock) ──
  _check_plugin_lock_helper(res)

  # ── Governance bypass coverage ──
  enforcer_path = CORTEX_REPO / "plugins" / "governance-enforcer" / "__init__.py"
  if enforcer_path.exists():
    enforcer_src = enforcer_path.read_text()
    checks = [
      ("WRITE_TOOLS includes execute_code", '"execute_code"' in enforcer_src),
      ("WRITE_TOOLS includes memory", '"memory"' in enforcer_src),
      ("WRITE_TOOLS includes text_to_speech", '"text_to_speech"' in enforcer_src),
      ("CONDITIONAL_WRITE_TOOLS includes process", '"process"' in enforcer_src),
      ("WRITE_PROCESS_ACTIONS defined", "WRITE_PROCESS_ACTIONS" in enforcer_src),
      ("python3 -c pattern present", r"(python|python3)\s.*-c" in enforcer_src),
      ("bash -c pattern present", r"(bash|sh|zsh)\s+-c" in enforcer_src),
      ("script-exec pattern (python3 .py etc)", r"python3(?:\.\d+)?" in enforcer_src),
      ("script-exec pattern (node .js etc)", r"node|ruby|perl" in enforcer_src),
      ("fail-closed crash handler", "GOVERNANCE ENFORCER CRASHED" in enforcer_src),
      ("pipe not caught as write (no [>|>>])", "[>|>>]" not in enforcer_src),
      ("grouped passwd alternation", r"(usermod|groupmod|useradd|groupadd|passwd)\s" in enforcer_src),
      ("read-check before write-check", "read-only terminal fast-path" in enforcer_src.lower()),
      ("no pip|npm in broad catch-all", "dpkg|brew" in enforcer_src and "pip|npm" not in enforcer_src.split("dpkg")[0]),
    ]
    all_pass = True
    for label, ok in checks:
      all_pass = all_pass and ok
    if all_pass:
      res.add("Governance coverage", "PASS", "all bypass closures validated")
    else:
      for label, ok in checks:
        if not ok:
          res.add(f"Governance gap ({label})", "FAIL",
              f"enforcer source is missing required guard",
              f"Update {enforcer_path} to include the missing guard")

    if state_dir.exists():
      # Lock files named .governance-{session_id}.json where session_id
      # is a timestamp-based UUID (e.g. 20260725_164953_750cbfe2) or a
      # cron/background session id (e.g. cron_<hash>_20260731_120022).
      # Files with a descriptive slug instead of a session ID (e.g.
      # .governance-fix-auth-bug.json) are legacy — flag them.
      legacy = [
        f for f in state_dir.glob(".governance-*.json")
        if not re.search(r"\d{8}_\d{6}", f.name)
      ]
      if legacy:
        for lf in legacy:
          res.add(f"Legacy lock ({lf.name})", "WARN",
              "slug-based naming superseded by session-scoped locks",
              f"Remove: rm -f {lf}")
  else:
    res.add("Governance coverage", "INFO", "enforcer source not found in repo")

  # ── Git hooks verification ──
  # When core.hooksPath is set globally, git ignores .git/hooks/ entirely.
  # Any files or symlinks there are misleading dead weight — flag for removal.
  # Only the deployed hooks at CORTEX_HOME/hooks/ are active.
  hooks_via_global = bool(global_hooks_path.rstrip("/") == expected_hooks_path)
  repo_hooks_dir = CORTEX_REPO / ".git" / "hooks"
  deployed_hooks_dir = CORTEX_HOME / "hooks"
  for hook_name in ("pre-commit", "pre-push", "post-commit", "post-merge", "post-push"):
    deployed_hook = deployed_hooks_dir / hook_name
    git_hook = repo_hooks_dir / hook_name
    repo_source = CORTEX_REPO / ".hermes-cortex" / "hooks" / hook_name

    # Check 1: deployed hook exists
    if not deployed_hook.exists():
      res.add(f"Hook: {hook_name} (deployed)", "FAIL",
          f"missing at {deployed_hook}",
          "REQUIRED: Run: cortex-update.sh ")
      continue
    res.add(f"Hook: {hook_name} (deployed)", "PASS", f"present at {deployed_hook}")

    # Check 2: .git/hooks/ artifacts
    if hooks_via_global:
      # global hooksPath is set — .git/hooks/ is ignored by git entirely.
      # Any file or symlink there is misleading dead weight.
      if git_hook.is_symlink() or git_hook.exists():
        res.add(f"Hook: {hook_name} (.git)", "WARN",
            f"redundant artifact — ignored by git (core.hooksPath is active)",
            f"REQUIRED: rm -f {git_hook}")
    elif git_hook.is_symlink() and os.readlink(str(git_hook)) == str(deployed_hook):
      res.add(f"Hook: {hook_name} (.git)", "PASS", f"symlinked to deployed copy")
    elif git_hook.exists():
      res.add(f"Hook: {hook_name} (.git)", "WARN",
          "standalone copy — won't auto-update",
          f"REQUIRED: rm {git_hook} && ln -sf {deployed_hook} {git_hook}")
    else:
      res.add(f"Hook: {hook_name} (.git)", "FAIL",
          f"not installed: {git_hook}",
          f"REQUIRED: ln -sf {deployed_hook} {git_hook}")

    # Check 3: deployed hook is a valid symlink (post-merge is intentionally standalone)
    if hook_name == 'post-merge':
      pass  # intentionally standalone — registered via register() in cortex-update.sh
    elif deployed_hook.is_symlink():
      target = os.readlink(str(deployed_hook))
      target_path = Path(target) if target.startswith('/') else deployed_hook.parent / target
      if target_path.exists():
        res.add(f'Hook: {hook_name} (symlink)', 'PASS',
            chr(8594) + ' ' + target)
      else:
        res.add(f'Hook: {hook_name} (symlink)', 'FAIL',
            f'symlink target missing: {target}',
            'REQUIRED: Run: cortex-update.sh to re-deploy hooks')
    else:
      res.add(f'Hook: {hook_name} (symlink)', 'WARN',
          'not a symlink — may drift from updated source',
          'REQUIRED: rm and re-deploy via cortex-update.sh')

    # Check 4: deployed hook content matches repo source (SHA256)
    if repo_source.exists() and deployed_hook.exists():
      dep_hash = hashlib.sha256(deployed_hook.read_bytes()).hexdigest()
      src_hash = hashlib.sha256(repo_source.read_bytes()).hexdigest()
      if dep_hash == src_hash:
        res.add(f"Hook: {hook_name} (content)", "PASS", "matches repo source")
      else:
        res.add(f"Hook: {hook_name} (content)", "FAIL",
            "deployed hook differs from repo source",
            f"REQUIRED: Run: cortex-update.sh ")

  # ── Redundant local git hooks (repos with own hooks despite core.hooksPath) ──
  # When core.hooksPath is set globally, local .git/hooks/ are NEVER consulted
  # by git. Any hooks there are misleading: agents may think they're active
  # when they're not, or worse, they may become active if core.hooksPath is
  # ever removed. Scan for them and flag for removal.
  managed_hooks = {"pre-commit", "pre-push", "post-commit", "post-merge"}
  search_dirs = [
    CORTEX_REPO.resolve(),
  ]
  # Also scan home-level .git dirs for other repos that might have hooks
  for d in HOME.iterdir():
    if not d.is_dir():
      continue
    git_dir = d / ".git"
    try:
      if git_dir.is_dir() and d not in search_dirs:
        search_dirs.append(d)
    except PermissionError:
      continue # can't access this directory — skip

  found_redundant = 0
  for repo_dir in sorted(set(search_dirs)):
    git_hooks = repo_dir / ".git" / "hooks"
    if not git_hooks.is_dir():
      continue
    for hook_file in git_hooks.iterdir():
      if hook_file.name in managed_hooks and hook_file.is_file() and not hook_file.name.endswith(".sample"):
        # This is a known managed hook in a local repo — redundant
        found_redundant += 1
        target = ""
        if hook_file.is_symlink():
          target = f" → {os.readlink(str(hook_file))}"
        res.add(f"Redundant hook ({repo_dir.name}/{hook_file.name})", "WARN",
            f"{hook_file}{target} — ignored by git when core.hooksPath is set",
            f"Remove: rm -f {hook_file}")

  if found_redundant == 0 and global_hooks_path.rstrip("/") == expected_hooks_path:
    res.add("Redundant local hooks", "PASS",
        "no redundant hooks found in local .git/hooks directories")

  # ── Bypass compliance check ──
  # If post-push hook left a bypass marker, refuse to pass until cleared.
  bypass_marker = state_dir / ".bypass-found"
  if bypass_marker.exists():
    bypass_details = bypass_marker.read_text().strip() if bypass_marker.stat().st_size > 0 else "unknown"
    res.add("Governance bypass", "FAIL",
        f"Bypass marker found: {bypass_marker}",
        f"Previous push had --no-verify commits. Fix and clear the marker:\n"
        f"  1. Re-do the commit through the pre-commit hook (no --no-verify)\n"
        f"  2. Push properly (no --no-verify on push either)\n"
        f"  3. rm -f {bypass_marker}")
  else:
    res.add("Governance bypass", "PASS", "no bypass markers found")

  # ── PENDING cycles ──
  # Unscored cycles indicate begin_change was called but feedback_accept
  # was never called. This is a governance leak.
  _loop_db = CORTEX_HOME / "data" / "loop-governance.db"
  _pending_count = 0
  if _loop_db.exists():
    try:
      import sqlite3
      _conn = sqlite3.connect(str(_loop_db))
      _conn.row_factory = sqlite3.Row
      _pending = _conn.execute(
        "SELECT id, task_id, cycle_num, session_id, timestamp FROM loop_cycles WHERE decision='PENDING' LIMIT 5000"
      ).fetchall()
      _pending_count = len(_pending)
      if _pending_count:
        # Auto-resolve cycles older than 24 hours (abandoned sessions)
        _now = datetime.now()
        _fresh = []
        _stale_count = 0
        for r in _pending:
          try:
            _ts = datetime.fromisoformat(r['timestamp'].replace('Z', ''))
          except (ValueError, TypeError):
            _ts = _now - timedelta(days=7)
          if (_now - _ts).total_seconds() > 86400:
            _conn.execute(
              "UPDATE loop_cycles SET decision='MOVE_ON', outcome_note='auto-resolved by health check — >24h stale' WHERE id=?",
              (r['id'],)
            )
            _stale_count += 1
          else:
            _fresh.append(r)
        _conn.commit()
        if _stale_count:
          res.add(f"PENDING cycles", "INFO",
              f"auto-resolved {_stale_count} cycle(s) >24h old (abandoned sessions)")
        if _fresh:
          def _fmt(r):
            sid = r['session_id'] or 'unknown'
            return f"{r['task_id']}#{r['cycle_num']} ({sid[:12]}...)"
          _lines = [_fmt(r) for r in _fresh]
          res.add(f"PENDING cycles", "FAIL",
              f"{len(_fresh)} unscored cycle(s): {', '.join(_lines[:5])}",
              f"Score them via feedback_accept or cancel with feedback_override")
        else:
          res.add("PENDING cycles", "PASS", "no unscored cycles")
      else:
        res.add("PENDING cycles", "PASS", "no unscored cycles")
      _conn.close()
    except Exception as _exc:
      res.add("PENDING cycles", "INFO", f"could not query: {_exc}")

  # ── Orphaned lock files ──
  # Lock files that exist but have no active MCP process.
  _lock_files = sorted(state_dir.glob(".governance-*.json"))
  if _lock_files:
    # Check if any are actually stale (no MCP server running)
    _mcp_running = bool(run_bg(["pgrep", "-f", "loop-gov-mcp"], timeout=5))
    if not _mcp_running:
      _names = ", ".join(f.name[:25] for f in _lock_files[:3])
      res.add("Orphaned locks", "FAIL",
          f"{len(_lock_files)} lock file(s) with no active MCP server: {_names}",
          f"Clean: rm -f {' '.join(str(f) for f in _lock_files)}")
    else:
      res.add("Orphaned locks", "PASS", f"{len(_lock_files)} lock(s), MCP server active")
  else:
    res.add("Orphaned locks", "PASS", "no lock files")

  # ── Skills gate presence ──
  # Verify the enforcer has the skills-loaded gate (structural enforcement)
  try:
    _enforcer_init = (plugin_src / "__init__.py").read_text()
    if "SKILLS_MARKER_DIR" in _enforcer_init:
      res.add("Skills gate", "PASS", "enforcer blocks writes without per-session skills markers")
    else:
      res.add("Skills gate", "WARN",
          "missing SKILLS_MARKER_DIR — skills gate not active",
          "Pull latest hermes-cortex and run cortex-update.sh")
  except (OSError, PermissionError):
    pass


def check_hook_drift(res):
    """Check deployed hooks match repo source — prevents stale hooks from
    bypassing orchestrator-only path restrictions.

    Each deployed hook in ~/.hermes-cortex/hooks/ should be a symlink
    pointing to ~/.hermes-cortex/scripts/<name>. Compare the content of
    the resolved script against the repo source in ops/scripts/.
    """
    import hashlib as _hl

    HOOKS_DIR = CORTEX_HOME / "hooks"
    REPO_HOOKS = CORTEX_REPO / "ops" / "scripts"
    if not HOOKS_DIR.is_dir():
        res.add("Hook content drift", "SKIP", "hooks directory not found")
        return

    # Hook → repo source mapping (pre-commit hook = pre-commit-score, etc.)
    HOOK_MAP = {
        "pre-commit": "pre-commit-score",
        "pre-push": "pre-push-pull",
        "post-commit": "post-commit-audit",
        "post-push": "post-push-audit",
        # post-merge is standalone — not checked here
    }

    for hook_name, repo_name in sorted(HOOK_MAP.items()):
        hook_path = HOOKS_DIR / hook_name
        if not hook_path.exists():
            res.add(f"Hook drift: {hook_name}", "FAIL",
                    f"hook not found at {hook_path}",
                    f"Run: cortex-update.sh to deploy hooks")
            continue

        # Deployed: resolve symlink → compare target file
        if hook_path.is_symlink():
            deployed_target = hook_path.resolve()
            while deployed_target.is_symlink():
                deployed_target = deployed_target.resolve()
        else:
            deployed_target = hook_path

        if not deployed_target.exists():
            res.add(f"Hook drift: {hook_name}", "FAIL",
                    f"symlink target {deployed_target} not found",
                    f"Run: cortex-update.sh to recreate hook")
            continue

        # Repo source
        repo_source = REPO_HOOKS / repo_name
        if not repo_source.exists():
            res.add(f"Hook drift: {hook_name}", "INFO",
                    f"repo source {repo_source} not found — skipping")
            continue

        # Compare content
        try:
            dep_md5 = _hl.md5(deployed_target.read_bytes()).hexdigest()
            src_md5 = _hl.md5(repo_source.read_bytes()).hexdigest()
        except OSError:
            res.add(f"Hook drift: {hook_name}", "WARN",
                    "could not read file for hash comparison")
            continue

        if dep_md5 == src_md5:
            res.add(f"Hook drift: {hook_name}", "PASS",
                    f"deployed matches repo ({dep_md5[:8]})")
        else:
            res.add(f"Hook drift: {hook_name}", "FAIL",
                    f"deployed {deployed_target.name} ({dep_md5[:8]}) != repo {repo_name} ({src_md5[:8]})",
                    f"Run: cortex-update.sh to redeploy hook")


def check_local_hooksPath_overrides(res):
  """7b. Scan all git repos for local core.hooksPath overrides that subvert the global setting.

  When core.hooksPath is set globally, git respects it for ALL repos.
  A local core.hooksPath (per-repo override) replaces the global setting
  for that repo only, effectively bypassing the global governance hooks.

  This check finds every git repo under $HOME and verifies its local
  core.hooksPath either matches the global or is unset.
  """
  global_hooks_path = run_bg(["git", "config", "--global", "core.hooksPath"], timeout=5)
  if not global_hooks_path:
    res.add("Local hooksPath override check", "SKIP",
        "Global core.hooksPath not set — cannot compare")
    return

  global_hooks = global_hooks_path.strip().rstrip("/")

  # Find all git repos under HOME
  try:
    raw = subprocess.run(
      ["find", str(HOME), "-maxdepth", "4", "-name", ".git", "-type", "d"],
      capture_output=True, text=True, timeout=15,
    ).stdout.strip()
  except (subprocess.TimeoutExpired, OSError):
    res.add("Local hooksPath override check", "INFO",
        "could not scan home directory for git repos")
    return

  if not raw:
    return

  EXCLUDED = {
    HOME / ".git",
    HOME / ".oh-my-zsh",
    HOME / ".hermes",
    HOME / ".brain",
    HOME / "__MACOSX",
    HOME / "Desktop",
    HOME / "Documents",
    HOME / "Downloads",
    HOME / "Music",
    HOME / "Pictures",
    HOME / "Videos",
    HOME / "Library",
    HOME / "Public",
    HOME / "Templates",
    HOME / "backups",
    HOME / "docker-data",
    HOME / "langfuse",
  }

  override_found = 0
  for path in raw.split("\n"):
    path = path.strip()
    if not path:
      continue
    repo_dir = Path(path).parent.resolve()
    skip = any(str(repo_dir).startswith(str(excl)) for excl in EXCLUDED)
    if skip:
      continue

    # Check local core.hooksPath
    local_hooks = run_bg(
      ["git", "-C", str(repo_dir), "config", "--local", "core.hooksPath"],
      timeout=5,
    ).strip()

    if not local_hooks:
      continue # no local override — inheriting global, good

    local_hooks = local_hooks.rstrip("/")
    if local_hooks == global_hooks:
      continue # local override matches global — benign

    # Mismatch found: local override differs from global
    override_found += 1
    res.add(f"Local hooksPath override ({repo_dir.name})", "FAIL",
        f"core.hooksPath → '{local_hooks}' (global is '{global_hooks}')",
        f"Remove override: git -C {repo_dir} config --unset core.hooksPath "
        f"(or set it to '{global_hooks}' if intentional)")

  if override_found == 0:
    res.add("Local hooksPath override check", "PASS",
        "no per-repo overrides — all repos inherit global hooksPath")


def check_install(res):
  """8. Install footprint: core files and directories present."""
  missing = []
  for rel_path, kind, desc in CORE_FOOTPRINT:
    p = HOME / rel_path
    if kind == "d" and not p.is_dir():
      missing.append((desc, rel_path))
    elif kind == "f" and not p.is_file():
      missing.append((desc, rel_path))

  if not missing:
    res.add("Install footprint", "PASS", "all core paths present")
  else:
    for desc, rel_path in missing[:5]:
      res.add(f"Install ({desc})", "FAIL", f"missing: {rel_path}",
          f"Run: bash {INSTALL_SCRIPT}")
    if len(missing) > 5:
      res.add(f"Install ({len(missing)} missing)", "FAIL", "run install.sh to fix")

  if SYMLINK_AUDIT.exists():
    out = run_bg(["bash", str(SYMLINK_AUDIT)], timeout=15)
    if "BROKEN" in out or "MISMATCH" in out:
      res.add("Symlinks", "WARN", "some symlinks need attention",
          "Run: bash ~/hermes-cortex/ops/scripts/manage/symlink-audit.sh")
    elif "ALL OK" in out or "OK" in out:
      res.add("Symlinks", "PASS", "all symlinks valid")
    else:
      res.add("Symlinks", "INFO", "symlink audit ran (check output manually)")


def check_stale_deploys(res):
  """Check ~/.hermes-cortex/scripts/ for orphaned or mis-deployed files."""
  cortex_update = Path.home() / "hermes-cortex" / "ops" / "scripts" / "cortex-update.sh"
  if not cortex_update.exists():
    return

  content = cortex_update.read_text()
  deploy_home = Path.home() / ".hermes-cortex"
  destinations = set()

  for line in content.splitlines():
    line = line.strip()
    if not (line.startswith("register ") or line.startswith("register_orch ")) or line.startswith("#"):
      continue
    m = re.match(r'register(?:_orch)?\s+"([^"]+)"\s+"([^"]+)"', line)
    if not m:
      continue
    src = m.group(1)
    dest_str = m.group(2)
    dest_str = dest_str.replace("${CORTEX_DEPLOY_HOME}", str(deploy_home))
    dest_str = dest_str.replace("${HOME}", str(Path.home()))
    dest = Path(dest_str)

    # On non-orch hosts, skip register_orch entries (they don't deploy here)
    if line.startswith("register_orch ") and AGENT_ROLE != "orchestrator":
      continue

    destinations.add(dest)

    repo_src = Path.home() / "hermes-cortex" / src
    if not repo_src.exists():
      res.add("Deploy source missing", "FAIL",
          f"{src} → {dest_str}",
          f"Remove register line for {src} in cortex-update.sh")

    if dest.is_symlink():
      # Resolve the symlink target — if it's a known register() destination,
      # this is an intentional cortex-managed symlink (e.g. hook → script).
      # The symlink "prevents drift" — when the source updates, the hook
      # automatically follows without a redeploy. Skip the warning.
      resolved = dest.resolve()
      if resolved in destinations:
        res.add(f"Deploy symlink: {dest.name}", "INFO",
            f"intentional — resolved to registered path {resolved.relative_to(deploy_home)}")
      else:
        res.add(f"Deploy symlink: {dest.name}", "WARN",
            "Should be a copy, not a symlink",
            f"Run: cp --remove-destination $(readlink {dest}) {dest}")
    elif dest.exists():
      if not dest.is_file():
        res.add(f"Deploy not regular: {dest.name}", "WARN",
            "Not a regular file",
            f"Remove and re-deploy: rm {dest} && cortex-update.sh ")

  scripts_dir = deploy_home / "scripts"
  if scripts_dir.exists():
    # Local-only no_agent cron scripts — NOT in repo, created per-host.
    # They are intentionally absent from register() mappings; must not be
    # flagged as stale. Mirrors the preserve list in cortex-update.sh
    # clean_stale_deploys(). (2026-08-02: adding the doctor cron-runtime
    # check surfaced these as "stale" — they were already preserved by the
    # deployer, the doctor just didn't know about them.)
    preserve = {
      "agent-daily-bible-reading.py",
      "local-clickhouse-log-cleanup.sh",
      "local-push-metrics.sh",
    }
    for f in sorted(scripts_dir.rglob("*")):
      if f.is_file() and f.suffix in (".py", ".sh") and "__pycache__" not in str(f):
        if f in destinations or f.name in preserve:
          continue
        size = f.stat().st_size
        res.add(f"Stale deploy: {f.relative_to(deploy_home)}", "WARN",
            f"{size:,} bytes — not in any register() mapping",
            f"Remove: rm {f}")


def check_stale_skills(res):
  """Check deployed skills for orphans (no repo source) and missing (not deployed).

  Scans ~/.hermes/skills/<cat>/<name>/ vs ~/hermes-cortex/skills/<cat>/<name>/
  and vs Hermes Agent default & optional skills.

  Orphans are flagged as WARN. Missing skills (repo has them, deployed doesn't)
  are flagged as INFO with remediation hint.
  """
  repo_skills = CORTEX_REPO / "skills"
  deployed_skills = HERMES_HOME / "skills"
  hermes_agent_dir = HERMES_HOME / "hermes-agent"

  if not repo_skills.is_dir() or not deployed_skills.is_dir():
    return

  def _index_skills(root: Path) -> dict:
    """Build {(cat, name): path} from root/<cat>/<name>/SKILL.md.
    Also builds set of skill names (without category) for fuzzy matching."""
    result = {}
    if not root.is_dir():
      return result
    for cat_dir in root.iterdir():
      if not cat_dir.is_dir() or cat_dir.name.startswith("."):
        continue
      for skill_dir in cat_dir.iterdir():
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
          result[(cat_dir.name, skill_dir.name)] = skill_md
    return result

  # ── Build indexes ──
  deployed = _index_skills(deployed_skills)
  repo_sk = _index_skills(repo_skills)

  # Hermes defaults: both skills/ and optional-skills/
  hermes_sk = {}
  for subdir in ("skills", "optional-skills"):
    hermes_sk.update(_index_skills(hermes_agent_dir / subdir))

  # Build set of Hermes default skill names (without category) for loose matching
  hermes_names = {name for (_cat, name) in hermes_sk}

  # ── 1. Orphaned deployed skills ──
  orphans = []
  for (cat, name) in sorted(deployed.keys()):
    in_repo = (cat, name) in repo_sk
    in_hermes = (cat, name) in hermes_sk or name in hermes_names
    if not in_repo and not in_hermes:
      # Double-check: Hermes built-in skills have metadata.hermes in SKILL.md
      # even when not found in hermes_agent_dir (e.g. on macOS where the
      # path may differ). Skip these — they're not orphans.
      try:
        skill_md = deployed[(cat, name)]
        fm_text = skill_md.read_text().split('---', 2)
        if len(fm_text) >= 2 and 'metadata:\n  hermes:' in fm_text[1]:
          continue  # Hermes built-in skill — not an orphan
      except (OSError, ValueError, KeyError):
        pass
      orphans.append(f"{cat}/{name}")

  if orphans:
    res.add(f"Stale skills: orphaned", "WARN",
        f"{len(orphans)} deployed skill(s) have no repo or Hermes source: {', '.join(orphans[:12])}",
        f"Remove: rm -rf ~/.hermes/skills/<cat>/<name> for each orphan, or add to repo/skills/")
  else:
    res.add("Stale skills: orphans", "PASS", "all deployed skills have a repo or Hermes source")

  # ── 2. Missing deployed skills ──
  missing = []
  for (cat, name) in sorted(repo_sk.keys()):
    if (cat, name) not in deployed:
      missing.append(f"{cat}/{name}")

  if missing:
    res.add(f"Stale skills: missing", "INFO",
        f"{len(missing)} repo skill(s) not deployed: {', '.join(missing[:12])}",
        f"Run: cortex-update.sh")
  else:
    res.add("Stale skills: missing", "PASS", "all repo skills are deployed")

  # ── 3. Ambiguous skill names (same name in multiple categories) ──
  def _find_ambiguous(indexes, label):
    """Detect when the same skill name appears in multiple categories."""
    name_cats = {}
    for (cat, name) in indexes:
      name_cats.setdefault(name, []).append(cat)
    ambiguous = {name: cats for name, cats in name_cats.items() if len(cats) > 1}
    if ambiguous:
      details = "; ".join(f"{name} → {', '.join(cats)}" for name, cats in sorted(ambiguous.items()))
      res.add(f"Stale skills: ambiguous names ({label})", "WARN",
          f"Skill name(s) exist in multiple categories: {details}",
          f"Consolidate into one category: rm -rf ~/.hermes/skills/<keep-cat>/<name> (delete duplicate).")
    else:
      res.add(f"Stale skills: ambiguous names ({label})", "PASS", "no duplicate skill names")

  _find_ambiguous(deployed.keys(), "deployed")
  _find_ambiguous(repo_sk.keys(), "repo")


def check_deploy_checksums(res):
  """Check MD5 checksums of deployed files vs repo source across ALL mappings.

  Covers three categories:
  1. register() entries in cortex-update.sh (scripts → ~/.hermes-cortex/scripts/)
  2. Non-register path mappings (plugins, AGENTS.md, SOUL.md, profiles)
  3. Governance plugin symlink vs copy detection
  """
  import hashlib as _hl

  repo_dir = CORTEX_REPO
  deploy_home = CORTEX_HOME
  if not repo_dir.is_dir():
    return

  def _md5(path):
    """Compute MD5 hex digest of a file. Returns None on error."""
    try:
      if path.is_file():
        return _hl.md5(path.read_bytes()).hexdigest()
    except (OSError, PermissionError):
      return None
    return None

  def _content_md5(path):
    """Compute MD5 hex digest of file content with SOURCE header stripped.

    cortex-update.sh adds a 2-line SOURCE header + blank to deployed .sh/.py
    files. Since 2026-08-02 the header sits BELOW the shebang (so direct
    ./script.py execution still works); legacy deployed files have the
    header at the top. Layouts stripped:
      #!/usr/bin/env python3      ← shebang (kept)
      # SOURCE: <path>            ← dropped
      # Do NOT edit this file — edit the source above and run: bash cortex-update.sh
      (blank)                     ← dropped
    or legacy:
      # SOURCE: <path>            ← dropped
      # Do NOT edit this file — edit the source above and run: bash cortex-update.sh
      (blank)                     ← dropped

    This function strips the header before computing the hash, so checksums
    match the repo source. Returns None on error.
    """
    try:
      if not path.is_file():
        return None
      raw = path.read_bytes()
      text = raw.decode("utf-8", errors="surrogateescape")
      lines = text.splitlines(keepends=True)
      # New layout: shebang line 0, header lines 1-3 → keep shebang, drop header
      if len(lines) >= 4 and lines[0].startswith("#!") and lines[1].startswith("# SOURCE:") and "Do NOT edit" in lines[2]:
        content = "".join([lines[0]] + lines[4:])
      # Legacy layout: header lines 0-2, content (incl. shebang) from line 3
      elif len(lines) >= 3 and lines[0].startswith("# SOURCE:") and "Do NOT edit" in lines[1]:
        # Strip the 3-line header
        content = "".join(lines[3:])
      else:
        content = text
      return _hl.md5(content.encode("utf-8", errors="surrogateescape")).hexdigest()
    except (OSError, PermissionError):
      return None

  def _check_pair(label, src_path, dest_path, res):
    """Check a single source→dest pair and report if MD5 differs.

    Uses _content_md5() for the deployed (dest) path to account for the
    3-line SOURCE header that cortex-update.sh prepends. Reports both
    the raw and stripped comparison for transparency.
    """
    src_md5 = _md5(src_path)
    dst_md5 = _md5(dest_path)
    dst_content_md5 = _content_md5(dest_path)

    if src_md5 is None and dst_md5 is None:
      return # neither exists — skip
    if src_md5 is None:
      res.add(f"Checksum: {label}", "WARN",
          f"source missing: {src_path.relative_to(repo_dir) if src_path.is_relative_to(repo_dir) else src_path}",
          f"File referenced but not found in repo — update register() entry")
      return
    if dst_md5 is None:
      res.add(f"Checksum: {label}", "WARN",
          f"deployed copy missing: {dest_path}",
          f"Run: cortex-update.sh ")
      return
    if src_md5 == dst_md5:
      res.add(f"Checksum: {label}", "PASS", "content matches repo source")
    elif dst_content_md5 is not None and src_md5 == dst_content_md5:
      res.add(f"Checksum: {label}", "PASS",
          f"content matches (after stripping SOURCE header)")
    else:
      res.add(f"Checksum: {label}", "FAIL",
          f"MD5 mismatch — deployed copy differs from repo source"
          f"{' (even after stripping SOURCE header)' if dst_content_md5 is not None else ''}",
          f"REQUIRED: Run: cortex-update.sh to resync")

  # ── Category 1: Parse register() entries from cortex-update.sh ──
  cortex_update = repo_dir / "ops" / "scripts" / "cortex-update.sh"
  if cortex_update.exists():
    content = cortex_update.read_text()
    for line in content.splitlines():
      line = line.strip()
      if not line.startswith("register ") or line.startswith("#"):
        continue
      m = re.match(r'register\s+"([^"]+)"\s+"([^"]+)"', line)
      if not m:
        continue
      src_rel = m.group(1)
      dest_str = m.group(2)
      dest_str = dest_str.replace("${CORTEX_DEPLOY_HOME}", str(deploy_home))
      dest_str = dest_str.replace("${HOME}", str(HOME))
      src_path = repo_dir / src_rel
      dest_path = Path(dest_str)
      if not dest_path.exists() and not src_path.exists():
        continue # both missing — skip silent (handled by check_stale_deploys)
      label = src_rel.split("/")[-1] # use filename as label
      _check_pair(label, src_path, dest_path, res)

  # ── Category 2: Non-register path mappings ──
  known_mappings = [
    # (label, repo_source_path, deployed_path)
    ("AGENTS.md", repo_dir / "AGENTS.md", HERMES_HOME / "AGENTS.md"),
    ("Governance plugin __init__.py", repo_dir / "plugins" / "governance-enforcer" / "__init__.py",
     HERMES_HOME / "plugins" / "governance-enforcer" / "__init__.py"),
    ("Governance plugin plugin.yaml", repo_dir / "plugins" / "governance-enforcer" / "plugin.yaml",
     HERMES_HOME / "plugins" / "governance-enforcer" / "plugin.yaml"),
    ("Governance plugin README.md", repo_dir / "plugins" / "governance-enforcer" / "README.md",
     HERMES_HOME / "plugins" / "governance-enforcer" / "README.md"),
  ]

  # Add profile-specific SOUL.md mapping for the current agent's local copy
  current_agent = os.environ.get("AGENT_NAME", "").lower().strip()
  if not current_agent:
    current_agent = os.uname().nodename.split(".")[0].lower().strip()
  if current_agent:
    local_soul = HERMES_HOME / "SOUL.md"
    if local_soul.exists():
      known_mappings.append(
        (f"SOUL.md (profile: {current_agent})", local_soul, local_soul)
      )

  for label, src, dst in known_mappings:
    _check_pair(label, src, dst, res)


def check_script_naming(res):
    """Check that cron script names match their cron names and follow prefix conventions."""
    if not JOBS_FILE.exists():
        return
    try:
        data = json.loads(JOBS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = job.get("name", "")
        script = job.get("script", "")
        if not name or not script:
            continue

        # Naming conventions apply only to no_agent jobs, where the script IS
        # the job. LLM-driven jobs (no_agent=False) may attach a shared
        # context-injection script (e.g. session-active-guard.py reused by
        # several *-workday crons) whose stdout is injected into the prompt —
        # its name is unrelated to the cron name by design.
        if not job.get("no_agent", False):
            continue

        script_stem = Path(script).stem  # e.g. 'agent-foo' from 'manage/agent-foo.sh'

        # Check 1: script name and cron name should share a base. Allow:
        # - script starts with cron name (agent-foo → agent-foo.py) ✅
        # - cron name starts with script name (agent-foo-weekday → agent-foo.py) ✅ (shared script)
        # Normalize: replace _ with - for comparison (agent-session_cache = agent-session-cache)
        script_norm = script_stem.replace("_", "-")
        name_norm = name.replace("_", "-")
        if not script_norm.startswith(name_norm) and not name_norm.startswith(script_norm):
            res.add(f"Script naming: {name}", "WARN",
                f"script '{script}' does not match cron name '{name}'",
                "Rename the script to match the cron name, or vice versa")

        # Check 2: script has correct prefix matching cron
        if name.startswith("agent-") and not script_stem.startswith("agent-"):
            res.add(f"Script prefix: {name}", "WARN",
                f"script '{script}' lacks 'agent-' prefix",
                f"Rename script to match cron name: {name}.sh (or .py)")
        elif name.startswith("orch-") and not script_stem.startswith("orch-"):
            res.add(f"Script prefix: {name}", "WARN",
                f"script '{script}' lacks 'orch-' prefix",
                f"Rename script to match cron name: {name}.sh (or .py)")
        elif name.startswith("local-") and not script_stem.startswith("local-"):
            res.add(f"Script prefix: {name}", "WARN",
                f"script '{script}' lacks 'local-' prefix",
                f"Rename script to match cron name: {name}.sh (or .py)")


def check_skills_version(res):
    """Check that all repo skills have a version field in frontmatter."""
    SKILLS_DIR = CORTEX_REPO / "skills"
    if not SKILLS_DIR.is_dir():
        return
    no_version = []
    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        try:
            content = skill_md.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if not re.search(r'^version:\s+\S', content, re.MULTILINE):
            name = "unknown"
            m = re.search(r'^name:\s+(.+)$', content, re.MULTILINE)
            if m:
                name = m.group(1).strip()
            rel_path = skill_md.relative_to(CORTEX_REPO)
            no_version.append((name, str(rel_path)))
    if no_version:
        for name, path in no_version[:10]:
            res.add(f"Skill version: {name}", "WARN",
                f"no version field — {path}",
                "Add 'version: 1.0.0' to SKILL.md frontmatter")
        if len(no_version) > 10:
            res.add(f"Skills version ({len(no_version)} total)", "WARN",
                f"{len(no_version) - 10} more skills missing version field",
                "Add version to all SKILL.md files")


def check_skill_fences(res):
    """Detect repo SKILL.md files with unbalanced markdown code fences.

    The agent-fixer has stripped trailing ``` fences from skills five times
    (change-test-loop: 14568284, 2214153d, f41f8f76, 297ffa9d + 2026-08-01
    working-tree corruption), and 134 skills were imported as truncated
    skill_view dumps (9a9efa91) with odd fence counts. An odd fence count
    corrupts rendering for every agent that loads the skill.
    """
    SKILLS_DIR = CORTEX_REPO / "skills"
    if not SKILLS_DIR.is_dir():
        return
    unbalanced = []
    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        try:
            content = skill_md.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        n = sum(1 for line in content.splitlines() if line.lstrip().startswith("```"))
        if n % 2 != 0:
            rel = skill_md.relative_to(CORTEX_REPO)
            unbalanced.append((n, str(rel)))
    if unbalanced:
        for n, path in unbalanced[:10]:
            res.add("Skill fences", "WARN", f"{path} — {n} fences (unbalanced)",
                "Restore the missing/stray fence (git checkout -- <file>)")
        if len(unbalanced) > 10:
            res.add(f"Skill fences ({len(unbalanced)} total)", "WARN",
                f"{len(unbalanced) - 10} more files unbalanced",
                "Most are 9a9efa91 truncated imports — re-collect from Joseph")


def check_skill_stubs(res):
    """Detect repo SKILL.md files that are truncated stubs.

    The Jul-17 imports (9a9efa91, 2347d26a, 70160929) landed 131 skills as
    ~1KB stubs because the old collect-agent-skills.sh truncated bus messages
    at 1000 chars. Stub files carry the literal 'Full content (truncated)'
    marker and cut off mid-content. Any agent that loads a stubbed skill gets
    a broken playbook — this is a FAIL, not a WARN.

    Recovery: the full content survives in agent-local
    state/skill-contents/idx_N.txt caches (always full — only delivery was
    cut). Run the fleet recovery: deploy agent-skill-stub-audit.py, EXEC it
    with --send on each source agent, then restore the returned content into
    skills/ and re-run cortex-update.
    """
    SKILLS_DIR = CORTEX_REPO / "skills"
    if not SKILLS_DIR.is_dir():
        return
    stubs = []
    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        try:
            content = skill_md.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        # Stubs are ~1KB. The size guard applies to BOTH markers — a full
        # doc that merely quotes 'Full content (truncated)' (e.g. the
        # hermes-cortex skill doc) is not a stub.
        if len(content) < 1500 and (
            "Full content (truncated)" in content
            or "--- End skill ---" in content
        ):
            rel = skill_md.relative_to(CORTEX_REPO)
            stubs.append((skill_md.stat().st_size, str(rel)))
    if stubs:
        for size, path in stubs[:10]:
            res.add("Skill stubs", "FAIL",
                f"{path} — {size} bytes, truncated (Full content (truncated))",
                "Replace with full copy from agent state/skill-contents cache: "
                "EXEC agent-skill-stub-audit.py --send on each source agent, then "
                "copy the returned full content over skills/ and run cortex-update.sh")
        if len(stubs) > 10:
            res.add(f"Skill stubs ({len(stubs)} total)", "FAIL",
                f"{len(stubs) - 10} more truncated skills",
                "Most are 9a9efa91 truncated imports — replace with full copies from agent caches")


def check_todo_db(res):
    """Check that todo-db.py exists and can reach Postgres."""
    todo_script = CORTEX_HOME / "scripts" / "todo-db.py"
    if not todo_script.is_file():
        res.add("Todo DB script", "FAIL",
            f"Not found at {todo_script}",
            "Run: cortex-update.sh to deploy todo-db.py")
        return

    # Quick connectivity test — run `todo-db.py pending` and check for valid JSON
    out = run_bg(["python3", str(todo_script), "pending"], timeout=15)
    if not out:
        res.add("Todo DB connectivity", "FAIL",
            "todo-db.py pending returned no output",
            "Check gbrain Postgres is running: sg docker -c 'docker ps | grep gbrain-postgres'")
        return

    try:
        data = json.loads(out)
        count = len(data) if isinstance(data, list) else 0
        res.add("Todo DB connectivity", "PASS", f"Postgres reachable, {count} pending item(s)")
    except (json.JSONDecodeError, TypeError):
        res.add("Todo DB connectivity", "FAIL",
            f"todo-db.py output not valid JSON: {out[:200]}",
            "Check gbrain Postgres: sg docker -c 'docker exec gbrain-postgres psql -U gbrain -d gbrain -c \"SELECT 1\"'")


def check_skill_drift(res):
    """Check for drift between repo source and deployed skills.

    Scans every skill in ~/.hermes/skills/ that has a matching path
    in ~/hermes-cortex/skills/. Reports which direction the drift is:

      PASS — deployed == repo source (in sync)
      WARN — repo source has changed, deploy pending (normal after edit)
      WARN — deployed copy is newer, repo source stale (agent forgot to commit)

    Skills without a repo counterpart (Hermes defaults) are skipped.
    """
    deploy_skills = HOME / ".hermes" / "skills"
    repo_skills = CORTEX_REPO / "skills"
    if not deploy_skills.is_dir() or not repo_skills.is_dir():
        return

    drifted = []  # (skill_name, direction, repo_md5, deployed_md5, mtime_detail)
    in_sync = 0
    skipped = 0

    for skill_md in sorted(deploy_skills.rglob("SKILL.md")):
        rel = skill_md.relative_to(deploy_skills)
        repo_md = repo_skills / rel

        if not repo_md.is_file():
            skipped += 1  # Hermes default — not ours
            continue

        try:
            dep_md5 = hashlib.md5(skill_md.read_bytes()).hexdigest()
            src_md5 = hashlib.md5(repo_md.read_bytes()).hexdigest()
        except (OSError, PermissionError):
            skipped += 1
            continue

        if dep_md5 == src_md5:
            in_sync += 1
            continue

        # Drift detected — determine direction via mtime (coarse) and git status
        skill_name = skill_md.parent.name
        cat_dir = skill_md.parent.parent.name
        label = f"{cat_dir}/{skill_name}"

        repo_mtime = repo_md.stat().st_mtime
        dep_mtime = skill_md.stat().st_mtime

        if dep_mtime > repo_mtime + 60:  # 1-minute tolerance for filesystem jitter
            direction = "deployed-newer"
            hint = f"Deployed copy is newer than repo source ({skill_md}). Commit the repo source before cortex-update overwrites it."
        elif repo_mtime > dep_mtime + 60:
            direction = "repo-newer"
            hint = f"Repo source has changed but deployed copy is stale ({repo_md}). Run cortex-update.sh."
        else:
            # Mtimes are within tolerance — treat as equal-content different
            direction = "content-mismatch"
            hint = f"Content differs but timestamps similar ({skill_md}). Likely needs cortex-update.sh."

        drifted.append((label, direction, hint))

    for label, direction, hint in drifted:
        if direction == "deployed-newer":
            res.add(f"Skill drift: {label}", "WARN", hint,
                "Copy the deployed changes to the repo source first, then commit.")
        else:
            res.add(f"Skill drift: {label}", "WARN", hint,
                "Run: cortex-update.sh")

    if not drifted and in_sync > 0:
        res.add("Skill drift", "PASS", f"{in_sync} skills in sync, {skipped} Hermes defaults skipped")
    elif in_sync > 0:
        res.add("Skill drift", "WARN",
            f"{len(drifted)} drifted, {in_sync} in sync, {skipped} Hermes defaults skipped",
            "Resolve each drift entry above")


def check_mycortex_parity(res):
    """Mycortex parity gate — RETIRED 2026-08-03.

    The parity gate was the gbrain→mycortex MIGRATION gate (prove the two
    engines retrieve equivalently BEFORE the flip). The flip happened; gbrain
    is deprecated and being removed. Comparing mycortex against gbrain-era
    golden expectations is obsolete — the golden set is retained as a
    regression fixture only, not a gate.

    Short-circuits to INFO (no subprocess, no 180s timeout) so every doctor
    run fleet-wide stops paying for a dead gate.
    """
    res.add("Mycortex parity gate", "INFO",
            "retired 2026-08-03 — gbrain deprecated; golden set kept as a mycortex regression fixture, not a gate")
    return


