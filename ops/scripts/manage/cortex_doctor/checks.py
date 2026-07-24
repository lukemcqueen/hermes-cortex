"""
Checks — all health check functions for cortex-doctor.

Each check_* function accepts a Results object and appends results.
"""

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
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
        pass
    return ""


def check_repo(res):
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
                    "REQUIRED: Run: cortex-update.sh --force-all")
        else:
            res.add("Deploy sync", "PASS", "deployed commit matches HEAD")
    else:
        res.add("Deploy sync", "WARN", "state/update-commit not found — deploy status unknown",
                "Run: cortex-update.sh --force-all (creates state/update-commit)")

    hermes_agents = Path.home() / ".hermes" / "AGENTS.md"
    if not hermes_agents.exists():
        res.add("AGENTS.md sync", "WARN", "~/.hermes/AGENTS.md missing",
                "REQUIRED: cp ~/hermes-cortex/AGENTS.md ~/.hermes/AGENTS.md")
    elif not hermes_agents.read_bytes() == repo_agents.read_bytes():
        res.add("AGENTS.md sync", "WARN", "~/.hermes/AGENTS.md content differs from repo",
                "REQUIRED: run cortex-update.sh --force-all (or cp if not deployed)")
    else:
        res.add("AGENTS.md sync", "PASS")


def check_dev_repo_agents(res):
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
                    f"Create: touch ~/{repo.name}/AGENTS.md  then add agent guidelines for this project")

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
            pass


def _extract_soul_markers(path):
    """Extract all named bold-marker sub-points from a SOUL.md's Behavioral Principles section.
    Returns a set of marker strings (e.g. 'Do real work', 'Verify every claim')."""
    if not path.exists():
        return set()
    text = path.read_text()
    # Find the Behavioral Principles section
    m = re.search(r'## Behavioral Principles\n(.*?)(?=\n## Scripture|\n## Final Directive|\n## Patterns|$)', text, re.DOTALL)
    if not m:
        return set()
    principles_text = m.group(1)
    # Extract all **bold** markers from list items
    markers = set()
    for line in principles_text.split('\n'):
        # Match: - **Marker** — description
        bm = re.search(r'^\s*-\s+\*\*([^*]+)\*\*', line)
        if bm:
            markers.add(bm.group(1).strip())
    return markers


def check_soul_sync(res):
    """Check SOUL.md is synced from repo template — for ALL agents."""
    template = CORTEX_REPO / "docs" / "templates" / "SOUL.md"
    if not template.exists():
        res.add("SOUL.md template", "WARN", "template not found at docs/templates/SOUL.md",
                "REQUIRED: verify repo is up to date")
        return

    template_markers = _extract_soul_markers(template)
    template_count = len(template_markers)

    def _check_one(label, path, fix_hint_prefix):
        """Check a single SOUL.md against the template."""
        if not path.exists():
            res.add(f"SOUL.md sync ({label})", "FAIL", f"{path} missing",
                    f"REQUIRED: {fix_hint_prefix}")
            return

        agent_markers = _extract_soul_markers(path)
        agent_count = len(agent_markers)

        # Check principle count first
        if template_count > agent_count + 2:  # allow small variance for agent-specific bullets
            missing = template_count - agent_count
            res.add(f"SOUL.md sync ({label})", "FAIL",
                    f"Template has {template_count} markers, {path.name} has {agent_count} — {missing} missing",
                    f"REQUIRED: Run: python3 ~/hermes-cortex/ops/scripts/manage/soul-merge.py")
            return

        # Check for missing content markers
        missing_markers = template_markers - agent_markers
        if missing_markers:
            # Filter out agent-specific sub-points that don't apply
            # (e.g. agent-specific maintainer instructions)
            critical_missing = {m for m in missing_markers
                                if not any(skip in m for skip in
                                           ["This principle absorbs", "Template verse", "Replace with"])}
            if critical_missing:
                res.add(f"SOUL.md sync ({label})", "FAIL",
                        f"Missing {len(critical_missing)} sub-points from template: {', '.join(sorted(critical_missing)[:5])}",
                        f"REQUIRED: Run: python3 ~/hermes-cortex/ops/scripts/manage/soul-merge.py")
                return

        res.add(f"SOUL.md sync ({label})", "PASS")

    # Check deployed copy
    hermes_soul = Path.home() / ".hermes" / "SOUL.md"
    _check_one("~/.hermes", hermes_soul,
               "cp ~/hermes-cortex/docs/templates/SOUL.md ~/.hermes/SOUL.md && customize for your role")

    # Check ALL agent profiles in the repo
    profiles_dir = CORTEX_REPO / "profiles" / "personal" / "agent-profiles"
    if profiles_dir.exists():
        for profile_path in sorted(profiles_dir.iterdir()):
            if profile_path.is_dir() and (profile_path / "SOUL.md").exists():
                soul_path = profile_path / "SOUL.md"
                agent_name = profile_path.name
                _check_one(f"repo:{agent_name}", soul_path,
                          f"cp ~/.hermes/SOUL.md {soul_path} (sync deployed → repo)")


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
            if not any(name.startswith(p) for p in ["orch-", "agent-", "local-", "system-"]):
                continue
            orphan_crons.append(name)
    if orphan_crons:
        res.add(f"Orphan crons: {len(orphan_crons)}", "INFO",
                f"Not in expected list: {', '.join(orphan_crons[:5])}",
                "Run: hermes cron remove <name> for each orphan")
    else:
        res.add("Crons: orphans", "PASS", "no unexpected crons found")

    expected_set = set(expected_crons)
    extra = [str(n) for n in registered if n not in expected_set]
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
    hostname = run_bg(["hostname", "-s"]).strip() or "unknown"
    is_orch = hostname in ("moses", "esther")
    if orch_crons_list:
        missing_orch = [n for n in orch_crons_list if n not in registered]
        if is_orch and missing_orch:
            res.add("Orch crons missing", "FAIL",
                    f"orchestrator host '{hostname}' missing {len(missing_orch)}: {', '.join(missing_orch)}",
                    "Run: bash install-orch-crons.sh --force")
        elif is_orch and not missing_orch:
            res.add("Orch crons", "PASS",
                    f"all {len(orch_crons_list)} orchestrator crons present (host: {hostname})")
        elif not is_orch and not missing_orch:
            res.add("Orch crons", "INFO",
                    f"orchestrator crons exist on non-orch host '{hostname}' (ok if backup)")

    res.add("Crons total", "PASS" if len(registered) > 0 else "WARN", f"{len(registered)} jobs registered")


def check_scripts(res):
    """3. Script integrity: all scripts referenced by crons exist."""
    if not JOBS_FILE.exists():
        return
    try:
        data = json.loads(JOBS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return

    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    script_dirs = [HERMES_HOME / "scripts", CORTEX_HOME / "scripts", HOME / ".local" / "bin"]
    missing = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        script = job.get("script", "")
        if not script:
            continue
        found = False
        for d in script_dirs:
            if (d / script).exists():
                found = True
                break
        if not found and Path(script).is_absolute() and Path(script).exists():
            found = True
        if not found:
            missing.append((job.get("name", "?"), script))

    if not missing:
        res.add("Script integrity", "PASS", "all cron scripts found")
    else:
        for name, script in missing[:5]:
            res.add(f"Script ({name})", "FAIL", f"not found: {script}",
                    "Run: bash cortex-update.sh --force-all")


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
        pass

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
        req = urllib.request.Request(f"{bus_url}/api/pgmq/queues/{queue}")
        if creds:
            req.add_header("Authorization", f"{scheme} {creds}")
        resp = urllib.request.urlopen(req, timeout=8)
        q_info = json.loads(resp.read().decode())
        pending_count = q_info.get("pending_count", 0)
        processing_count = q_info.get("processing_count", 0)
        if processing_count > 0:
            res.add("Bus stuck msgs", "FAIL",
                    f"{processing_count} message(s) stuck in 'processing' state for {queue}",
                    "Handler is crashing before archive — run: git pull && cortex-update.sh --force-all")
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
                f"Run: cortex-update.sh --force-all (expected at {handler_path})")


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
        deployed_hash = _hl.md5(deployed.read_bytes()).hexdigest()
        repo_hash = _hl.md5(repo_source.read_bytes()).hexdigest()

        if deployed_hash != repo_hash:
            res.add("Doctor version", "WARN",
                    "Running older version — repo source differs",
                    "Run: cortex-update.sh --force-all")
        else:
            res.add("Doctor version", "PASS", "Deployed version matches repo")
    except Exception as e:
        res.add("Doctor self", "SKIP", f"Version check error: {e}")


def check_services(res):
    """4. Service health: external endpoints, Ollama, gbrain, bus, and self-version."""
    _check_self_stale(res)
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

    # gbrain daemon
    if IS_MAC:
        out = run_bg(["launchctl", "list", "com.gbrain.autopilot"], timeout=5)
        if '"PID"' in out:
            res.add("gbrain daemon", "PASS", "autopilot active (launchd)")
        else:
            out2 = run_bg(["launchctl", "list", "com.gbrain.sync-watch"], timeout=5)
            if '"PID"' in out2:
                res.add("gbrain daemon", "PASS", "sync-watch active (launchd, legacy)")
            else:
                res.add("gbrain daemon", "WARN", "Neither autopilot nor sync-watch active",
                        "Run: bash ~/hermes-cortex/ops/scripts/install/install-gbrain-sync.sh")
    else:
        out = run_bg(["systemctl", "--user", "is-active", "gbrain-autopilot"], timeout=5)
        if out.strip() == "active":
            res.add("gbrain daemon", "PASS", "autopilot active (systemd)")
        else:
            out2 = run_bg(["systemctl", "--user", "is-active", "com.gbrain.sync-watch"], timeout=5)
            if out2.strip() == "active":
                res.add("gbrain daemon", "PASS", "sync-watch active (systemd, legacy)")
            else:
                res.add("gbrain daemon", "WARN", "Neither autopilot nor sync-watch active",
                        "Run: bash ~/hermes-cortex/ops/scripts/install/install-gbrain-sync.sh")

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
                    "sudo systemctl disable --now hermes-dashboard hermes-health hermes-inbox hermes-gateway ; "
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
                    pass

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
    expected_user_units = {
        "hermes-cortex-dashboard.service",
        "hermes-cortex-langfuse.service",
        "hermes-cortex-agent-bus.service",
        "gbrain-autopilot.service",
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
                "Run: cortex-update.sh --force-all or hermes-services-apply.py")

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
                    f"Re-deploy: cortex-update.sh --force-all")
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
                        "Run: cortex-update.sh --force-all  OR  generate agent card in that directory")

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
                        "Renew cert: sudo certbot renew  OR  set CORTEX_SSL_CERT_PATH env var")

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


def check_governance(res):
    """7. Governance system: plugin, pre-commit hook, MCP servers, lock files, score-cycle."""
    config_text = read_file(CONFIG_FILE)
    state_dir = CORTEX_HOME / "state"
    hooks_dir = CORTEX_HOME / "hooks"
    global_hooks_path = run_bg(["git", "config", "--global", "core.hooksPath"], timeout=5)

    # ── Governance plugin ──
    plugin_dir = HERMES_HOME / "plugins" / "governance-enforcer"
    plugin_src = CORTEX_REPO / "plugins" / "hermes-governance-enforcer"
    plugin_enabled = "governance-enforcer" in config_text and "enabled" in config_text

    if plugin_dir.exists() and (plugin_dir / "__init__.py").exists():
        res.add("Governance plugin", "PASS", "installed at ~/.hermes/plugins/governance-enforcer")
        if plugin_dir.is_symlink():
            target = os.readlink(str(plugin_dir))
            if plugin_src.exists() and str(plugin_src) in target:
                res.add("Plugin symlink", "PASS", f"symlinked to {target}")
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
                        "Re-create: ln -sf ~/hermes-cortex/plugins/hermes-governance-enforcer ~/.hermes/plugins/")
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
                            "REQUIRED: rm -rf ~/.hermes/plugins/governance-enforcer && "
                            "ln -sf ~/hermes-cortex/plugins/hermes-governance-enforcer ~/.hermes/plugins/"
                            " (replace copy with symlink so git pull keeps it fresh)")
            else:
                res.add("Plugin content", "WARN",
                        "can't compare — source or deployed __init__.py missing")
    else:
        res.add("Governance plugin", "FAIL", "not installed",
                "Install: ln -sf ~/hermes-cortex/plugins/hermes-governance-enforcer ~/.hermes/plugins/\n"
                "Then: hermes plugins enable governance-enforcer --allow-tool-override\n"
                "Then: /reset (new session)")

    if plugin_enabled:
        res.add("Plugin config", "PASS", "enabled in config.yaml")
    else:
        res.add("Plugin config", "FAIL" if plugin_dir.exists() else "WARN",
                "not enabled in config.yaml",
                "Run: hermes plugins enable governance-enforcer --allow-tool-override")

    if plugin_src.exists() and (plugin_src / "__init__.py").exists():
        res.add("Plugin source", "PASS", "source in repo at plugins/hermes-governance-enforcer")
    else:
        res.add("Plugin source", "FAIL", "source missing in repo",
                "Check: ~/hermes-cortex/plugins/hermes-governance-enforcer/")

    # ── MCP servers ──
    for name, server_script in EXPECTED_MCP_SERVERS.items():
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
                    "Update: cp ~/hermes-cortex/ops/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit"
                    " (current hook is missing enforcer verification)")
        else:
            res.add("Pre-commit hook", "WARN", "installed but may be outdated",
                    "Run: cp ~/hermes-cortex/ops/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit")
    else:
        res.add("Pre-commit hook", "FAIL", f"not found at {expected_hook_path}",
                "Install: cp ~/hermes-cortex/ops/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit\n"
                "Then: chmod +x ~/.hermes-cortex/hooks/pre-commit")

    # ── Pre-push hook ──
    expected_push_hook = hooks_dir / "pre-push"
    if expected_push_hook.exists():
        push_content = expected_push_hook.read_text()
        if "pre-push-pull" in push_content:
            res.add("Pre-push hook", "PASS", "installed with pull-before-push check")
        else:
            res.add("Pre-push hook", "WARN", "installed but may be outdated")
    else:
        res.add("Pre-push hook", "WARN", "not installed",
                "Install: cp ~/hermes-cortex/ops/scripts/pre-push-pull ~/.hermes-cortex/hooks/pre-push\n"
                "Then: chmod +x ~/.hermes-cortex/hooks/pre-push")

    # ── Score-cycle CLI ──
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
        if found_score.is_symlink():
            target = os.readlink(str(found_score))
            if Path(target).exists():
                res.add("Score-cycle", "PASS", f"available at {found_score} → {target}")
            else:
                res.add("Score-cycle", "WARN", f"symlink broken: {found_score} → {target}",
                        "Re-run: bash ~/hermes-cortex/core/governance/setup.sh")
        else:
            res.add("Score-cycle", "PASS", f"available at {found_score}")
    else:
        res.add("Score-cycle", "WARN", "not found in PATH",
                "Run: bash ~/hermes-cortex/core/governance/setup.sh to deploy scoring tools")

    # ── Stale governance locks ──
    if not state_dir.exists():
        res.add("State directory", "INFO", "does not exist (will be created on first begin_change)")
    else:
        lock_files = list(state_dir.glob(".governance-*.json"))
        if lock_files:
            stale_count = 0
            now = time.time()
            for lf in lock_files:
                try:
                    lock_data = json.loads(lf.read_text())
                    started = lock_data.get("started_at", "")
                    if started:
                        try:
                            started_ts = datetime.fromisoformat(started).timestamp()
                            age_hours = (now - started_ts) / 3600
                            if age_hours > 24:
                                stale_count += 1
                                res.add(f"Stale lock ({lf.name})", "WARN",
                                        f"from {started} ({age_hours:.0f}h old)",
                                        f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
                        except (ValueError, TypeError):
                            stale_count += 1
                            res.add(f"Stale lock ({lf.name})", "WARN",
                                    f"unparseable timestamp: {started}",
                                    f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
                    else:
                        stale_count += 1
                        res.add(f"Stale lock ({lf.name})", "WARN",
                                "no started_at field",
                                f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
                except (json.JSONDecodeError, OSError):
                    stale_count += 1
                    res.add(f"Stale lock ({lf.name})", "WARN",
                            "unparseable lock file",
                            f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")

            if stale_count == 0:
                res.add("Governance locks", "PASS",
                        f"{len(lock_files)} active lock(s), none stale")
        else:
            res.add("Governance locks", "PASS", "no lock files")

    # ── Governance bypass coverage ──
    enforcer_path = CORTEX_REPO / "plugins" / "hermes-governance-enforcer" / "__init__.py"
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
            ("read-check before write-check", "read-only fast-path" in enforcer_src),
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
            legacy = [
                f for f in state_dir.glob(".governance-*.json")
                if not f.name.startswith(".governance-sess_")
            ]
            if legacy:
                for lf in legacy:
                    res.add(f"Legacy lock ({lf.name})", "WARN",
                            "slug-based naming superseded by session-scoped locks",
                            f"Remove: rm -f {lf}")
    else:
        res.add("Governance coverage", "INFO", "enforcer source not found in repo")

    # ── Git hooks verification ──
    repo_hooks_dir = CORTEX_REPO / ".git" / "hooks"
    deployed_hooks_dir = CORTEX_HOME / "hooks"
    for hook_name in ("pre-commit", "post-commit", "post-merge"):
        deployed_hook = deployed_hooks_dir / hook_name
        git_hook = repo_hooks_dir / hook_name
        repo_source = CORTEX_REPO / ".hermes-cortex" / "hooks" / hook_name

        # Check 1: deployed hook exists
        if not deployed_hook.exists():
            res.add(f"Hook: {hook_name} (deployed)", "FAIL",
                    f"missing at {deployed_hook}",
                    "REQUIRED: Run: cortex-update.sh --force-all")
            continue
        res.add(f"Hook: {hook_name} (deployed)", "PASS", f"present at {deployed_hook}")

        # Check 2: .git/hooks/ is a symlink to deployed
        if git_hook.is_symlink() and os.readlink(str(git_hook)) == str(deployed_hook):
            res.add(f"Hook: {hook_name} (.git)", "PASS", f"symlinked to deployed copy")
        elif git_hook.exists():
            res.add(f"Hook: {hook_name} (.git)", "WARN",
                    "standalone copy — won't auto-update",
                    f"REQUIRED: rm {git_hook} && ln -sf {deployed_hook} {git_hook}")
        else:
            res.add(f"Hook: {hook_name} (.git)", "FAIL",
                    f"not installed: {git_hook}",
                    f"REQUIRED: ln -sf {deployed_hook} {git_hook}")

        # Check 3: deployed hook content matches repo source (MD5)
        if repo_source.exists() and deployed_hook.exists():
            dep_hash = hashlib.sha256(deployed_hook.read_bytes()).hexdigest()
            src_hash = hashlib.sha256(repo_source.read_bytes()).hexdigest()
            if dep_hash == src_hash:
                res.add(f"Hook: {hook_name} (content)", "PASS", "matches repo source")
            else:
                res.add(f"Hook: {hook_name} (content)", "FAIL",
                        "deployed hook differs from repo source",
                        f"REQUIRED: Run: cortex-update.sh --force-all")


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
        if not line.startswith("register ") or line.startswith("#"):
            continue
        m = re.match(r'register\s+"([^"]+)"\s+"([^"]+)"', line)
        if not m:
            continue
        src = m.group(1)
        dest_str = m.group(2)
        dest_str = dest_str.replace("${CORTEX_DEPLOY_HOME}", str(deploy_home))
        dest_str = dest_str.replace("${HOME}", str(Path.home()))
        dest = Path(dest_str)
        destinations.add(dest)

        repo_src = Path.home() / "hermes-cortex" / src
        if not repo_src.exists():
            res.add("Deploy source missing", "FAIL",
                    f"{src} → {dest_str}",
                    f"Remove register line for {src} in cortex-update.sh")

        if dest.is_symlink():
            res.add(f"Deploy symlink: {dest.name}", "WARN",
                    "Should be a copy, not a symlink",
                    f"Run: cp --remove-destination $(readlink {dest}) {dest}")
        elif dest.exists():
            if not dest.is_file():
                res.add(f"Deploy not regular: {dest.name}", "WARN",
                        "Not a regular file",
                        f"Remove and re-deploy: rm {dest} && cortex-update.sh --force-all")

    scripts_dir = deploy_home / "scripts"
    if scripts_dir.exists():
        for f in sorted(scripts_dir.rglob("*")):
            if f.is_file() and f.suffix in (".py", ".sh") and "__pycache__" not in str(f):
                if f not in destinations:
                    size = f.stat().st_size
                    res.add(f"Stale deploy: {f.relative_to(deploy_home)}", "WARN",
                            f"{size:,} bytes — not in any register() mapping",
                            f"Remove: rm {f}")


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

    def _check_pair(label, src_path, dest_path, res):
        """Check a single source→dest pair and report if MD5 differs."""
        src_md5 = _md5(src_path)
        dst_md5 = _md5(dest_path)

        if src_md5 is None and dst_md5 is None:
            return  # neither exists — skip
        if src_md5 is None:
            res.add(f"Checksum: {label}", "WARN",
                    f"source missing: {src_path.relative_to(repo_dir) if src_path.is_relative_to(repo_dir) else src_path}",
                    f"File referenced but not found in repo — update register() entry")
            return
        if dst_md5 is None:
            res.add(f"Checksum: {label}", "WARN",
                    f"deployed copy missing: {dest_path}",
                    f"Run: cortex-update.sh --force-all")
            return
        if src_md5 == dst_md5:
            res.add(f"Checksum: {label}", "PASS", "content matches repo source")
        else:
            res.add(f"Checksum: {label}", "FAIL",
                    f"MD5 mismatch — deployed copy differs from repo source",
                    f"REQUIRED: Run: cortex-update.sh --force-all to resync")

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
                continue  # both missing — skip silent (handled by check_stale_deploys)
            label = src_rel.split("/")[-1]  # use filename as label
            _check_pair(label, src_path, dest_path, res)

    # ── Category 2: Non-register path mappings ──
    known_mappings = [
        # (label, repo_source_path, deployed_path)
        ("AGENTS.md", repo_dir / "AGENTS.md", HERMES_HOME / "AGENTS.md"),
        ("Governance plugin __init__.py", repo_dir / "plugins" / "hermes-governance-enforcer" / "__init__.py",
         HERMES_HOME / "plugins" / "governance-enforcer" / "__init__.py"),
        ("Governance plugin plugin.yaml", repo_dir / "plugins" / "hermes-governance-enforcer" / "plugin.yaml",
         HERMES_HOME / "plugins" / "governance-enforcer" / "plugin.yaml"),
        ("Governance plugin README.md", repo_dir / "plugins" / "hermes-governance-enforcer" / "README.md",
         HERMES_HOME / "plugins" / "governance-enforcer" / "README.md"),
    ]

    # Add profile-specific SOUL.md mapping only for the current agent
    current_agent = os.environ.get("AGENT_NAME", "").lower().strip()
    if not current_agent:
        current_agent = os.uname().nodename.split(".")[0].lower().strip()
    if current_agent:
        profile_soul = repo_dir / "profiles" / "personal" / "agent-profiles" / current_agent / "SOUL.md"
        if profile_soul.exists():
            known_mappings.append(
                (f"SOUL.md (profile: {current_agent})", profile_soul, HERMES_HOME / "SOUL.md")
            )

    for label, src, dst in known_mappings:
        _check_pair(label, src, dst, res)
