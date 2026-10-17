"""cortex_doctor.task_integrity — the two ways task work goes invisible.

Both were found in the wild on 2026-10-04, each having hidden real work for weeks
while every board looked healthy:

1. SCHEMA DRIFT. The migration runner only sees migrations that are DEPLOYED, and a
   migration is only deployed if it is in `cortex-update.sh`'s register map (the
   register map IS the deploy). `v009`/`v010` — the entire v3 task model — were never
   registered, so the deployed schema dir stopped at `v008` and no host could ever
   apply them. A repo migration that is not registered is silent, permanent drift.

2. STRANDED SLICES. A slice that is `pending` WITH an assignee is excluded from the
   claim pool (`assignee IS NULL`) and is not `in_progress`, so no worker can take it
   and nobody is working it. Six sat like that for six weeks while the board counted
   them as ordinary pending work (18 shown, 9 actually claimable).

Both checks are read-only and lock-free. Where a check cannot verify, it says so
rather than passing silently — a check that cannot look must not read as "fine".
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_SCHEMA_GLOB = "v0*.sql"

# A `list --assigned` task row starts with the 8-char task-id prefix. Advisory
# lines name the tool that produced them instead, so they never match.
_ROW_ID = re.compile(r"^[0-9a-f]{8}\s")


def _is_orchestrator() -> bool:
    """Host-derived role, same rule as cortex_doctor.config.AGENT_ROLE.

    The probe uses the fleet view (`--repo ALL`) ONLY for an orchestrator so it
    can see stranded slices on every host; a worker keeps its repo-scoped view
    (it has no right to fleet-wide visibility).
    """
    agent_type = os.environ.get("AGENT_TYPE", "").lower().strip()
    if agent_type in ("orchestrator", "server", "dev"):
        return agent_type == "orchestrator"
    if os.environ.get("IS_ORCHESTRATOR", "").lower() in ("true", "1", "yes"):
        return True
    return os.uname().nodename.split(".")[0] in ("moses", "esther")


def _repo() -> Path:
    return Path(os.environ.get("CORTEX_REPO", Path.home() / "hermes-cortex"))


def _deploy() -> Path:
    return Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex"))


def _registered_schema() -> set:
    """Basenames of schema migrations that cortex-update.sh will actually deploy."""
    update = _repo() / "ops" / "scripts" / "cortex-update.sh"
    try:
        text = update.read_text()
    except OSError:
        return set()
    out = set()
    for line in text.splitlines():
        if line.strip().startswith("register") and "tasks/schema/" in line:
            out.add(Path(line.split('"')[1]).name)
    return out


def _run(cmd: list, timeout: int = 25, cwd=None) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=cwd)
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


def check_task_model_integrity(res: "Results") -> None:            # noqa: F821
    """1d. Task model: migrations actually deploy, and no slice is stranded."""
    schema_dir = _repo() / "ops" / "services" / "tasks" / "schema"
    if not schema_dir.is_dir():
        return

    local = sorted(p.name for p in schema_dir.glob(_SCHEMA_GLOB))
    if not local:
        return

    # ── (1) every migration must be registered, or it never reaches a host ──
    registered = _registered_schema()
    unregistered = [n for n in local if n not in registered]
    if unregistered:
        res.add(
            "Task schema deploy",
            "FAIL",
            f"{len(unregistered)} migration(s) in the repo are NOT in the deploy "
            f"register, so the version-gated runner can never apply them on a host: "
            f"{', '.join(unregistered[:4])}",
            "Add a register() line per migration to ops/scripts/cortex-update.sh "
            "(the register map IS the deploy)",
        )
    else:
        res.add("Task schema deploy", "PASS",
                f"all {len(local)} task migrations are in the deploy register")

    # ── (1b) the DEPLOYED copy must also carry them ──
    deployed_dir = _deploy() / "services" / "tasks" / "schema"
    if deployed_dir.is_dir():
        deployed = {p.name for p in deployed_dir.glob(_SCHEMA_GLOB)}
        missing = [n for n in local if n not in deployed]
        if missing:
            res.add(
                "Task schema deployed", "WARN",
                f"{len(missing)} registered migration(s) are not on the deployed "
                f"tree: {', '.join(missing[:4])}",
                "Run: bash ops/scripts/cortex-update.sh",
            )
        else:
            res.add("Task schema deployed", "PASS",
                    f"all {len(local)} migrations present on the deployed tree")

    # ── (1c) is the DB itself behind the repo? ──
    migrator = _deploy() / "services" / "tasks" / "migrate.py"
    runner = _deploy() / "scripts" / "task-db.py"
    if migrator.is_file() and runner.is_file():
        raw = _run(["python3", str(runner), "--apply-schema", "--dry-run"])
        if not raw.strip():
            res.add("Task schema version", "WARN",
                    "COULD NOT VERIFY: the migration runner produced no output",
                    "Check psql/docker access, then re-run the doctor")
        else:
            pending = len(re.findall(r"pending|would apply|applying", raw, re.I))
            m = re.search(r"current=(\d+)", raw)
            if m and pending:
                res.add("Task schema version", "WARN",
                        f"the DB is at version {m.group(1)} but the repo has "
                        f"unapplied migration(s)",
                        "Run: python3 ~/.hermes-cortex/scripts/task-db.py --apply-schema")
            elif m:
                res.add("Task schema version", "PASS",
                        f"DB at version {m.group(1)}, no pending migrations")
            else:
                res.add("Task schema version", "PASS", raw.strip().splitlines()[-1][:70])

    # ── (2) no slice may be pending-with-an-assignee (unclaimable AND unwatched) ──
    # `list --assigned` is repo-scoped and answers "repo unknown" when it cannot
    # resolve one — which is what it did on EVERY doctor run, because the probe
    # left the resolution to the invoker's cwd. Pass the repo root as the
    # subprocess cwd so the check can actually look, and read any advisory as
    # "could not verify" instead of letting its text count as a task row.
    if runner.is_file():
        # An orchestrator sees the whole fleet (--repo ALL); a worker only its
        # own repo (resolved from the repo root the probe passes as cwd — the
        # verdict must never depend on the invoker's cwd).
        cmd = ["python3", str(runner), "list", "--assigned"]
        if _is_orchestrator():
            cmd += ["--repo", "ALL"]
        raw = _run(cmd, cwd=str(_repo()))
        if not raw.strip():
            res.add("Stranded slices", "WARN",
                    "COULD NOT VERIFY: task-db list --assigned returned nothing",
                    "Check psql/docker access, then re-run the doctor")
        elif "repo unknown" in raw:
            res.add("Stranded slices", "WARN",
                    "COULD NOT VERIFY: task-db could not resolve a repo, so the "
                    "assigned-and-unstarted slice list was never checked (the "
                    "verdict would otherwise depend on the invoker's cwd)",
                    "Run the doctor from a repo working copy, or set "
                    "CORTEX_SESSION_REPO; then re-run the doctor")
        elif "(no unstarted hand-offs" in raw:
            res.add("Stranded slices", "PASS", "no pending slice is assigned-and-unstarted")
        else:
            rows = [ln for ln in raw.splitlines() if _ROW_ID.match(ln)]
            if not rows:
                res.add("Stranded slices", "WARN",
                        "COULD NOT VERIFY: task-db printed neither rows nor a "
                        "no-hand-offs marker — its output format may have changed",
                        f"Inspect: python3 {runner} list --assigned")
            else:
                res.add(
                    "Stranded slices", "WARN",
                    f"{len(rows)} slice(s) are pending WITH an assignee: unclaimable "
                    f"(the pool needs assignee IS NULL) and not in_progress, so nothing "
                    f"is working them",
                    "Release them to the pool: task-db.py unclaim <id> --reason '<why>' "
                    "(or list them with: task-db.py list --assigned)",
                )
