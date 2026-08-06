#!/usr/bin/env python3
"""
Task DB — persistent cross-session task storage for Hermes Cortex agents.

Enterprise task/workflow engine (party-reviewed design, 2026-08-06):
docs/design/task-workflow.md. Replaces the old bus.todos todo-db.py.

Storage: `tasks` schema on per-host mycortex-postgres (every agent has it).
CRUD connects as mycortex_reader_<profile> (NEVER superuser — party B-2);
DDL (--apply-schema) delegates to ops/services/tasks/migrate.py as the DB owner.

Security invariants (party B-1 — no injection, no shell RCE):
  - Query text flows via psql STDIN only — never embedded in a shell command
    string (the old `sg docker -c "...-c <query>"` path was shell-injectable).
  - Identifier-ish values (agent/project/repo/target/assignee/scope/status/
    source/column) are validated against strict allowlists BEFORE use.
  - Free text (content, tags) is quote-doubled into string literals
    (safe under standard_conforming_strings=on, PG default).
  - ON_ERROR_STOP=1 on every psql call + stderr ERROR: scan (belt+braces).
  - All DML funnels through tasks.task_upsert() — the single write path
    that enforces status/column coherence (party B-4).

Usage:
    task-db.py list    [--agent <name>] [--status <s>] [--project <p>]
                       [--scope <s>] [--repo <r>] [--assignee <a>]
                       [--due-before <iso>] [--tag <t>]
    task-db.py add     <content> [--agent <name>] [--priority 0-3]
                       [--project <p>] [--repo <r>] [--target <host>]
                       [--scope personal|fleet] [--assignee <a>]
                       [--due <iso>] [--tag <t> ...] [--source <s>]
    task-db.py update  <id> --status <new-status>
    task-db.py pending             # print pending as JSON (session restore)
    task-db.py restore <json>      # bulk restore from JSON (session start)
    task-db.py save-end            # archive completed/cancelled
    task-db.py prune [--older-than 90d]   # delete archived rows older than N
    task-db.py --apply-schema      # delegate to ops/services/tasks/migrate.py

Honest fleet semantics (party B-3): `--scope fleet` stores the row locally
on this host only — it is NOT visible fleet-wide until transport ships
(roadmap: git-backed, private repo). The CLI says so explicitly.
"""

import functools
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

# ── Config ────────────────────────────────────────────────────

MYCORTEX_CONFIG = os.path.expanduser("~/.hermes-cortex/mycortex.conf")
DEFAULT_DB = os.environ.get("TASK_DB_NAME", "mycortex")
CONTAINER = "mycortex-postgres"
PG_OPTS = ["-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "||"]

# ── Allowlists (party B-1) ────────────────────────────────────

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SCOPES = ("personal", "fleet")
STATUSES = ("pending", "in_progress", "completed", "cancelled")
COLUMNS = ("backlog", "todo", "in_progress", "review", "done")
SOURCES = ("dream", "session", "manual", "bridge", "governance", "inbox",
           "doctor-probe")


def _valid_name(value: str | None) -> bool:
    """Identifier-ish columns are constrained names — never free text."""
    return value is None or bool(NAME_RE.match(value))


def _check_name(flag: str, value: str | None) -> None:
    if not _valid_name(value):
        print(f"ERROR: {flag} '{value}' invalid — use letters/digits/._- only "
              f"(max 64 chars), no paths.", file=sys.stderr)
        sys.exit(2)


def _check_enum(flag: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        print(f"ERROR: {flag} '{value}' invalid — must be one of: {', '.join(allowed)}",
              file=sys.stderr)
        sys.exit(2)


def _check_priority(value: int) -> None:
    if not (0 <= value <= 3):
        print("ERROR: --priority must be 0-3 (0 unset, 1 normal, 2 high, 3 urgent)",
              file=sys.stderr)
        sys.exit(2)


def _check_uuid(value: str) -> None:
    if not UUID_RE.match(value):
        print(f"ERROR: '{value}' is not a valid task UUID", file=sys.stderr)
        sys.exit(2)


# ── Profile resolution (same order as install-profile-reader-role.sh) ──
def resolve_profile() -> str:
    """HERMES_PROFILE → AGENT_NAME → hostname. Never scans profiles/*/."""
    return (os.environ.get("HERMES_PROFILE")
            or os.environ.get("AGENT_NAME")
            or platform.node() or "default")


PROFILE = resolve_profile()
# TASK_DB_ROLE env override: tests connect as a scratch role (L2 hermeticity).
CRUD_ROLE = os.environ.get("TASK_DB_ROLE", f"mycortex_reader_{PROFILE}")


# ── psql plumbing (stdin-only, no shell embedding — party B-1) ──

@functools.lru_cache(maxsize=4)
def _get_db_query(role: str) -> list[str]:
    """Return platform-appropriate psql invocation (query via STDIN).

    Linux → direct `docker exec -i` (docker group). If docker is
            unreachable, fall back to `sg docker -c` with the query STILL on
            stdin — the command string contains only fixed names/flags, never
            user data, so it is not shell-injectable.
    macOS → direct psql reading ~/.hermes-cortex/mycortex.conf (or defaults).
    """
    if platform.system() == "Darwin":
        if os.path.exists(MYCORTEX_CONFIG):
            with open(MYCORTEX_CONFIG) as f:
                cfg = json.load(f)
            url = cfg.get("database_url", f"postgresql://{role}:@127.0.0.1:15432/{DEFAULT_DB}")
        else:
            url = f"postgresql://{role}:@127.0.0.1:15432/{DEFAULT_DB}"
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return [
            shutil.which("psql") or "/opt/homebrew/bin/psql",
            "-h", parsed.hostname or "127.0.0.1",
            "-p", str(parsed.port or 15432),
            "-U", parsed.username or role,
            "-d", DEFAULT_DB,
            *PG_OPTS,
        ]
    # Linux — direct docker exec (docker group)
    try:
        subprocess.run(["docker", "exec", CONTAINER, "true"],
                       capture_output=True, timeout=5, check=True)
        return ["docker", "exec", "-i", CONTAINER, "psql",
                "-U", role, "-d", DEFAULT_DB, *PG_OPTS]
    except Exception:
        # sg fallback — NO user data in the command string (stdin carries SQL).
        # The -F separator MUST be shell-quoted inside the sg string: unquoted
        # `-F ||` is a shell OR → "syntax error near unexpected token `||'"
        # (psql-automation pitfall, verified by test_linux_branch_sg_fallback).
        return ["sg", "docker", "-c",
                f"docker exec -i {CONTAINER} psql -U {role} -d {DEFAULT_DB} "
                "-v ON_ERROR_STOP=1 -t -A -F '||'"]


def _sql_literal(value: str) -> str:
    """Quote-double a value into a SQL string literal (B-1)."""
    return "'" + value.replace("'", "''") + "'"


def build_query(sql: str, params: list | None = None) -> str:
    """Pure function: interpolate ? params into a SQL template.

    The ONLY value-escaping primitive in this module. Values land in
    string-literal positions (single-quote doubling, safe under
    standard_conforming_strings=on). Callers MUST allowlist/validate
    identifier-ish values BEFORE calling — this function does not guess.
    """
    if not params:
        return sql
    out = sql
    for p in params:
        idx = out.find("?")
        if idx < 0:
            raise ValueError(f"too many params for query: {sql[:80]}...")
        if p is None:
            repl = "NULL"
        elif isinstance(p, bool):
            repl = "TRUE" if p else "FALSE"
        elif isinstance(p, (int, float)):
            repl = str(p)
        elif isinstance(p, (list, tuple)):
            repl = "ARRAY[" + ",".join(_sql_literal(str(x)) for x in p) + "]"
        else:
            repl = _sql_literal(str(p))
        out = out[:idx] + repl + out[idx + 1:]
    if "?" in out:
        raise ValueError(f"missing params for query: {sql[:80]}...")
    return out


def psql(query: str, params: list | None = None, role: str | None = None,
         timeout: int = 15) -> str:
    """Run a SQL query via psql stdin; return trimmed stdout.

    Exits 1 on any error (rc≠0 OR stderr contains ERROR:). Never silent —
    the F-04 no-op failure mode is structurally impossible here.
    """
    full_query = build_query(query, params)
    cmd = _get_db_query(role or CRUD_ROLE)
    try:
        result = subprocess.run(cmd, input=full_query, capture_output=True,
                                text=True, timeout=timeout)
    except FileNotFoundError as e:
        print(f"ERROR: {e.filename} not found — is psql/docker installed?",
              file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0 or "ERROR:" in result.stderr:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        print(f"ERROR: {detail[:500]}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


# ── Row parsing (||-delimited, -F '||') ───────────────────────

def parse_row(line: str) -> dict | None:
    """Parse a ||-delimited psql output line into a dict. Malformed → None."""
    parts = [p.strip() for p in line.split("||")]
    if len(parts) < 21:
        return None

    def _int(v):  # tolerant int
        try:
            return int(v) if v else 0
        except ValueError:
            return 0

    def _null(v):  # psql prints NULL as '' by default; 'NULL' if \pset null
        return None if (not v or v == "NULL") else v

    def _tags(v):
        if not v or v == "NULL":
            return []
        return [t for t in v.split(",") if t]

    return {
        "id": parts[0], "content": parts[1], "created_by": parts[2],
        "assignee": _null(parts[3]), "project": parts[4],
        "repo": _null(parts[5]), "target": _null(parts[6]),
        "scope": parts[7], "status": parts[8], "column": _null(parts[9]),
        "position": _int(parts[10]), "priority": _int(parts[11]),
        "due": _null(parts[12]), "tags": _tags(parts[13]),
        "source": parts[14], "depends_on": _null(parts[15]),
        "session_id": _null(parts[16]), "created_at": parts[17],
        "updated_at": parts[18], "status_changed_at": parts[19],
        "completed_at": _null(parts[20]),
    }


SELECT_COLS = (
    "id, content, created_by, assignee, project, repo, target, "
    "scope, status, \"column\", \"position\", priority, due, "
    "tags, source, depends_on, session_id, created_at, "
    "updated_at, status_changed_at, completed_at"
)


# ── Commands ──────────────────────────────────────────────────

def cmd_list(agent: str | None, status: str | None, project: str | None,
             scope: str | None, repo: str | None, assignee: str | None,
             tag: str | None, due_before: str | None):
    """List tasks — union of personal + locally-present fleet rows (B-3)."""
    for flag, val, checker in (
        ("--agent", agent, _check_name), ("--project", project, _check_name),
        ("--repo", repo, _check_name), ("--assignee", assignee, _check_name),
    ):
        checker(flag, val)
    if status:
        _check_enum("--status", status, STATUSES)
    if scope:
        _check_enum("--scope", scope, SCOPES)

    params = [agent, status, scope, project, repo, assignee, tag]
    sql = build_query(
        f"SELECT {SELECT_COLS} FROM tasks.task_list(?, ?, ?, ?, ?, ?, ?, 500);",
        params,
    )
    raw = psql(sql)
    if not raw:
        print("No tasks found.")
        return

    header = f"{'ID':<38} {'Agent':<10} {'Scope':<9} {'Status':<12} {'Pr':<3} Content"
    print(header)
    print("-" * len(header))
    for line in raw.split("\n"):
        row = parse_row(line)
        if not row:
            continue
        print(f"{row['id']:<38} {row['created_by']:<10} {row['scope']:<9} "
              f"{row['status']:<12} {row['priority']:<3} {row['content']}")


def cmd_add(content: str, agent: str | None, priority: int, project: str | None,
            repo: str | None, target: str | None, scope: str | None,
            assignee: str | None, due: str | None, tags: list[str],
            source: str | None):
    """Add a new task."""
    agent = agent or PROFILE
    for flag, val, checker in (
        ("--agent", agent, _check_name), ("--project", project, _check_name),
        ("--repo", repo, _check_name), ("--target", target, _check_name),
        ("--assignee", assignee, _check_name),
    ):
        checker(flag, val)
    if scope:
        _check_enum("--scope", scope, SCOPES)
    if source:
        _check_enum("--source", source, SOURCES)
    _check_priority(priority)
    if due:
        # basic ISO sanity — full validation happens in Postgres
        if not re.match(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$", due):
            print(f"ERROR: --due '{due}' not ISO 8601 (e.g. 2026-08-10 or 2026-08-10T14:00Z)",
                  file=sys.stderr)
            sys.exit(2)

    new_id = str(uuid.uuid4())
    session_id = os.environ.get("HERMES_SESSION_ID", "")
    psql(
        "SELECT tasks.task_upsert(?::uuid, ?, ?, ?, ?, ?, ?, ?, 'pending', "
        "NULL, NULL, ?, ?::timestamptz, ?, ?, ?, ?);",
        [new_id, content, agent, assignee, project or "hermes-cortex",
         repo, target, scope or "personal", priority, due or None,
         tags or None, source or "manual", None, session_id or None],
    )
    print(f"✅ Task added: {new_id[:8]}... — {content}")
    if (scope or "personal") == "fleet":
        print("⚠️  fleet task stored LOCALLY on this host only — not visible "
              "fleet-wide until transport ships (roadmap: git-backed, private repo).")


def cmd_update(task_id: str, new_status: str):
    """Update a task's status (canonical lifecycle, B-4)."""
    _check_uuid(task_id)
    _check_enum("--status", new_status, STATUSES)
    psql(
        "SELECT tasks.task_upsert(?::uuid, NULL, NULL, NULL, NULL, NULL, NULL, "
        "NULL, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);",
        [task_id, new_status],
    )
    print(f"✅ Task {task_id[:8]}... → {new_status}")


def cmd_pending():
    """Print pending/in_progress tasks as JSON for session restore."""
    raw = psql(
        f"SELECT {SELECT_COLS} FROM tasks.task_list(?, NULL, NULL, NULL, NULL, "
        f"NULL, NULL, 500);",
        [PROFILE],
    )
    items = []
    for line in raw.split("\n"):
        row = parse_row(line)
        if not row or row["status"] not in ("pending", "in_progress"):
            continue
        items.append({
            "id": row["id"], "content": row["content"],
            "agent_name": row["created_by"], "status": row["status"],
            "session_id": row["session_id"], "priority": row["priority"],
            "project": row["project"], "repo": row["repo"], "scope": row["scope"],
        })
    print(json.dumps(items, indent=2))


def cmd_restore(json_file: str):
    """Bulk-restore tasks from a JSON file (session start)."""
    if not os.path.exists(json_file):
        print(f"No restore file: {json_file} — starting fresh.")
        return
    with open(json_file) as f:
        items = json.load(f)
    if not items:
        print("No pending tasks to restore.")
        return

    count = 0
    for item in items:
        _check_uuid(item["id"])
        psql(
            "SELECT tasks.task_upsert(?::uuid, ?, ?, NULL, ?, NULL, NULL, ?, ?, "
            "NULL, NULL, ?, NULL, NULL, ?, NULL, ?);",
            [item["id"], item["content"], item.get("agent_name", PROFILE),
             item.get("project", "hermes-cortex"),
             item.get("scope", "personal"), item.get("status", "pending"),
             item.get("priority", 0), item.get("source", "session"),
             item.get("session_id")],
        )
        count += 1
    print(f"✅ Restored {count} pending task(s) from {json_file}")


def cmd_save_end():
    """Session-end: archive completed/cancelled, keep pending."""
    result = psql("SELECT tasks.task_archive_old(?);", [PROFILE])
    archived = result.strip()
    print(f"Archived {archived} completed/cancelled task(s) for {PROFILE}.")

    pending = psql(
        f"SELECT count(*) FROM tasks.task_list(?, NULL, NULL, NULL, NULL, "
        f"NULL, NULL, 500) WHERE status IN ('pending','in_progress');",
        [PROFILE],
    )
    if pending and int(pending) > 0:
        print(f"⚠️  {pending} pending task(s) remain for next session.")


def cmd_prune(older_than: str):
    """Delete ONLY archived rows older than N (never active rows)."""
    m = re.match(r"^(\d+)\s*(day|week|month|year)s?$", older_than)
    if not m:
        print("ERROR: --older-than must be like '90d', '2 weeks', '3 months'",
              file=sys.stderr)
        sys.exit(2)
    n, unit = int(m.group(1)), m.group(2)
    interval = {"day": "days", "week": "weeks", "month": "months", "year": "years"}[unit]
    result = psql("SELECT tasks.task_prune(make_interval(days => ?), ?);",
                  [n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit], PROFILE])
    print(f"Pruned {result.strip()} archived task(s) older than {older_than}.")


def cmd_apply_schema():
    """Delegate DDL to the version-gated migrate runner (as DB owner)."""
    candidates = [
        Path(os.environ.get("CORTEX_REPO", "")) / "ops/services/tasks/migrate.py",
        Path.home() / "hermes-cortex/ops/services/tasks/migrate.py",
        Path.home() / ".hermes-cortex/scripts/ops/services/tasks/migrate.py",
        Path.home() / ".hermes-cortex/services/tasks/migrate.py",
    ]
    migrate = next((c for c in candidates if c.exists()), None)
    if migrate is None:
        print("ERROR: ops/services/tasks/migrate.py not found (tried 4 paths)",
              file=sys.stderr)
        sys.exit(1)
    result = subprocess.run([sys.executable, str(migrate)], capture_output=True,
                            text=True, timeout=120)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        sys.exit(result.returncode)
    print(result.stdout.strip())


# ── CLI ───────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    def _flag(name: str, default=None):
        """Fetch a --flag value (supporting --flag value and --flag=value)."""
        for i in range(2, len(sys.argv)):
            if sys.argv[i] == name and i + 1 < len(sys.argv):
                return sys.argv[i + 1]
            if sys.argv[i].startswith(name + "="):
                return sys.argv[i][len(name) + 1:]
        return default

    def _flags(name: str) -> list[str]:
        """Fetch repeated --flag values."""
        out = []
        for i in range(2, len(sys.argv)):
            if sys.argv[i] == name and i + 1 < len(sys.argv):
                out.append(sys.argv[i + 1])
            elif sys.argv[i].startswith(name + "="):
                out.append(sys.argv[i][len(name) + 1:])
        return out

    if command == "list":
        cmd_list(
            _flag("--agent"), _flag("--status"), _flag("--project"),
            _flag("--scope"), _flag("--repo"), _flag("--assignee"),
            _flag("--tag"), _flag("--due-before"),
        )

    elif command == "add":
        content = None
        for i in range(2, len(sys.argv)):
            if i == 2 and not sys.argv[i].startswith("--"):
                content = sys.argv[i]
                break
        if not content:
            print("ERROR: content required. Usage: task-db.py add <content> [flags]",
                  file=sys.stderr)
            sys.exit(1)
        priority = int(_flag("--priority", "0"))
        cmd_add(
            content, _flag("--agent"), priority, _flag("--project"),
            _flag("--repo"), _flag("--target"), _flag("--scope"),
            _flag("--assignee"), _flag("--due"), _flags("--tag"),
            _flag("--source"),
        )

    elif command == "update":
        if len(sys.argv) < 4 or "--status" not in sys.argv:
            print("ERROR: Usage: task-db.py update <id> --status <new-status>",
                  file=sys.stderr)
            sys.exit(1)
        new_status = _flag("--status")
        if not new_status:
            print("ERROR: --status requires a value", file=sys.stderr)
            sys.exit(1)
        cmd_update(sys.argv[2], new_status)

    elif command == "pending":
        cmd_pending()

    elif command == "restore":
        cmd_restore(sys.argv[2] if len(sys.argv) > 2 else "/dev/stdin")

    elif command == "save-end":
        cmd_save_end()

    elif command == "prune":
        older_than = _flag("--older-than", "90d")
        if not older_than:
            older_than = "90d"
        cmd_prune(older_than)

    elif command == "--apply-schema":
        cmd_apply_schema()

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
