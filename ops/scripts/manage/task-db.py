#!/usr/bin/env python3
"""
Task DB — persistent cross-session task storage for Hermes Cortex agents.

Enterprise task/workflow engine (party-reviewed design, 2026-08-06):
docs/design/task-workflow.md. Replaces the old bus.todos todo-db.py.
Task Lifecycle v2 (party-reviewed 2026-08-06, docs/design/task-lifecycle-v2.md)
adds: story/slices, paused, bus-commands-as-tasks, Telegram visibility.

Storage: `tasks` schema on per-host mycortex-postgres (every agent has it).
CRUD connects as mycortex_reader_<profile> (NEVER superuser — party B-2);
DDL (--apply-schema) delegates to ops/services/tasks/migrate.py as the DB owner.

Security invariants (party B-1 — no injection, no shell RCE):
  - Query text flows via psql STDIN only — never embedded in a shell command
    string (the old `sg docker -c "...-c <query>"` path was shell-injectable).
  - Identifier-ish values (agent/project/repo/target/assignee/scope/status/
    source/column/kind) are validated against strict allowlists BEFORE use.
  - Free text (content, tags) is quote-doubled into string literals
    (safe under standard_conforming_strings=on, PG default).
  - ON_ERROR_STOP=1 on every psql call + stderr ERROR: scan (belt+braces).
  - All DML funnels through tasks.task_upsert() — the single write path
    that enforces status/column coherence (party B-4).
  - Notify is NON-FATAL, post-commit, and never prints to stdout
    (lib/telegram_notify.py; R-15 — logs go to a file).

Usage:
    task-db.py list    [--agent <name>] [--status <s>] [--project <p>]
                       [--scope <s>] [--repo <r>] [--assignee <a>]
                       [--due-before <iso>] [--tag <t>] [--parent <story-id>]
    task-db.py summary <story-id>     # v3: story slice-status summary
    task-db.py add     <content> [--agent <name>] [--priority 0-3]
                       [--project <p>] [--repo <r>] [--target <host>]
                       [--scope personal|fleet] [--assignee <a>]
                       [--due <iso>] [--tag <t> ...] [--source <s>]
                       [--parent <uuid>] [--kind story|slice]
                       [--correlation-id <bus-corr>] [--no-notify]
    task-db.py update  <id> --status <new-status> [--reason <r>]
                       [--no-notify]
    task-db.py update  --by-correlation <corr> --status <new-status>
    task-db.py switch  <target-id>        # pause current + resume target
    task-db.py pending             # print pending as JSON (session restore)
    task-db.py restore <json> [--include-inbox]
    task-db.py save-end            # archive completed/cancelled
    task-db.py prune [--older-than 90d]   # delete archived rows older than N
    task-db.py --apply-schema      # delegate to ops/services/tasks/migrate.py

Statuses: pending, in_progress, paused, completed, cancelled, blocked,
waiting (blocked/waiting are v3/v008 — schema v8+).

Honest fleet semantics (party B-3): `--scope fleet` stores the row locally
on this host only — it is NOT visible fleet-wide until transport ships
(roadmap: git-backed, private repo). The CLI says so explicitly.

v2 (TL-v2 S3): requires tasks schema v005+. Graceful degradation: on older
schema, paused/switch/--parent/--kind/--by-correlation are rejected with a
clear "requires v005" error and no events/notify are emitted.
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
STATUSES = ("pending", "in_progress", "paused", "completed", "cancelled",
            "blocked", "waiting")
KINDS = ("story", "slice")
COLUMNS = ("backlog", "todo", "in_progress", "review", "done")
SOURCES = ("dream", "session", "manual", "bridge", "governance", "inbox",
           "doctor-probe")
# v2 features require schema v005 (TL-v2 S3 — graceful degradation R-11)
V2_MIN_SCHEMA = 5
# v3 (v006-deferred) features require schema v008 (TL-v2 S6 — blocked/waiting
# status, story list --parent, task_story_summary)
V3_MIN_SCHEMA = 8


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


# ── Profile resolution (env → .env agent var → hostname) ──
def _env_agent_name() -> str:
    """Read AGENT_NAME from the canonical .env agent-identity files.

    Order: ~/.hermes-cortex/agent.env (per-host, gitignored) →
    ~/hermes-cortex/.env (consolidated env). Falls back to "".
    Never uses whoami/hostname as identity — the .env variable is the
    source of truth for the agent's identity (Luke directive 2026-08-10).
    """
    for path in (
        Path.home() / ".hermes-cortex" / "agent.env",
        Path.home() / "hermes-cortex" / ".env",
        Path.home() / ".hermes-cortex" / ".env",
    ):
        try:
            if path.is_file():
                for line in path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("AGENT_NAME="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            return val
        except OSError:
            continue
    return ""


def resolve_profile() -> str:
    """HERMES_PROFILE → AGENT_NAME env → .env agent var. ERROR if none.

    NEVER falls back to hostname (Luke directive 2026-08-10): identity must
    come from an explicit agent variable. A host without identity config is
    misconfigured — fail loudly rather than silently writing rows as the
    machine name.
    """
    profile = (os.environ.get("HERMES_PROFILE")
               or os.environ.get("AGENT_NAME")
               or _env_agent_name())
    if not profile:
        print("ERROR: cannot resolve agent identity — set AGENT_NAME in "
              "~/.hermes-cortex/agent.env or export HERMES_PROFILE/AGENT_NAME",
              file=sys.stderr)
        sys.exit(1)
    return profile


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


# ── Schema probe (TL-v2 S3 — graceful degradation R-11) ──────

def schema_version() -> int:
    """Return tasks.schema_version max (0 when schema missing/unreachable)."""
    try:
        raw = psql("SELECT max(version) FROM tasks.schema_version;")
        return int(raw) if raw.strip().isdigit() else 0
    except SystemExit:
        return 0


def _require_v2(feature: str) -> None:
    """Refuse a v2 feature when the tasks schema is older than v005."""
    if schema_version() < V2_MIN_SCHEMA:
        print(f"ERROR: {feature} requires tasks schema v{V2_MIN_SCHEMA}+ "
              f"(found v{schema_version()}). Run: bash cortex-update.sh",
              file=sys.stderr)
        sys.exit(2)


def _require_v3(feature: str) -> None:
    """Refuse a v3 (v006-deferred) feature when schema is older than v008."""
    if schema_version() < V3_MIN_SCHEMA:
        print(f"ERROR: {feature} requires tasks schema v{V3_MIN_SCHEMA}+ "
              f"(found v{schema_version()}). Run: bash cortex-update.sh",
              file=sys.stderr)
        sys.exit(2)


# ── Telegram notify (TL-v2 S2/S3 — non-fatal, never on stdout) ──

def _notify_import():
    """Import lib.telegram_notify with repo + deployed path fallbacks."""
    try:
        from lib.telegram_notify import notify as _n, format_task_message as _f
        return _n, _f
    except ImportError:
        pass
    # repo layout: ops/scripts/manage/task-db.py → ops/scripts on sys.path
    here = Path(__file__).resolve().parent
    for cand in (here.parent, here.parent.parent / "scripts",
                 Path.home() / ".hermes-cortex" / "scripts"):
        if str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
    try:
        from lib.telegram_notify import notify as _n, format_task_message as _f
        return _n, _f
    except ImportError:
        return None, None


_NOTIFY_CACHE = {}


def _notify_task(agent: str, kind: str | None, title: str, status: str,
                 task_id: str, parent_title: str | None = None) -> None:
    """Post a task-event Telegram message. Non-fatal; never raises.

    Suppressed for source='doctor-probe' rows (M-5) and by --no-notify.
    Mute/quiet/coalescing handled inside lib.telegram_notify.
    """
    if _NOTIFY_CACHE.get("disabled"):
        return
    if _NOTIFY_CACHE.get("imported") is None:
        imported = _notify_import()
        if imported[0] is None:
            _NOTIFY_CACHE["disabled"] = True  # lib absent — skip forever
            return
        _NOTIFY_CACHE["imported"] = imported
    notify, fmt = _NOTIFY_CACHE["imported"]
    try:
        msg = fmt(agent, kind or "flat", title or "", status, task_id,
                  parent_title)
        notify(msg, subject=f"[{agent}] task-event")
    except Exception:
        pass  # notify is NEVER fatal (design R-5)


# ── Row parsing (||-delimited, -F '||') ───────────────────────

def parse_row(line: str) -> dict | None:
    """Parse a ||-delimited psql output line into a dict. Malformed → None."""
    parts = [p.strip() for p in line.split("||")]
    if len(parts) < 24:
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
        "parent_id": _null(parts[21]), "kind": _null(parts[22]),
        "correlation_id": _null(parts[23]),
    }


# 21 legacy columns (task_list returns these) + 3 v005 columns selected
# directly from tasks.tasks (task_list does NOT return parent/kind/correlation).
SELECT_COLS = (
    "id, content, created_by, assignee, project, repo, target, "
    "scope, status, \"column\", \"position\", priority, due, "
    "tags, source, depends_on, session_id, created_at, "
    "updated_at, status_changed_at, completed_at, "
    "parent_id, kind, correlation_id"
)

# Same filters as tasks.task_list() but selects the v005 columns too.
# RLS (tasks_personal) protects this identically to the function.
# v3: --parent filters to a story's slices (parent_id = story id).
SELECT_SQL = (
    f"SELECT {SELECT_COLS} FROM tasks.tasks t "
    "WHERE (CAST(? AS text) IS NULL OR t.created_by = ?) "
    "AND (CAST(? AS text) IS NULL OR t.status = ?) "
    "AND (CAST(? AS text) IS NULL OR t.scope = ?) "
    "AND (CAST(? AS text) IS NULL OR t.project = ?) "
    "AND (CAST(? AS text) IS NULL OR t.repo = ?) "
    "AND (CAST(? AS text) IS NULL OR t.assignee = ?) "
    "AND (CAST(? AS text) IS NULL OR ? = ANY(t.tags)) "
    "AND (CAST(? AS uuid) IS NULL OR t.parent_id = ?) "
    "ORDER BY t.priority DESC, t.created_at ASC LIMIT 500"
)


# ── Commands ──────────────────────────────────────────────────

def cmd_list(agent: str | None, status: str | None, project: str | None,
             scope: str | None, repo: str | None, assignee: str | None,
             tag: str | None, due_before: str | None,
             parent: str | None = None):
    """List tasks — union of personal + locally-present fleet rows (B-3).

    v3: --parent <story-id> lists that story's slices (story `list --parent`).
    """
    for flag, val, checker in (
        ("--agent", agent, _check_name), ("--project", project, _check_name),
        ("--repo", repo, _check_name), ("--assignee", assignee, _check_name),
    ):
        checker(flag, val)
    if status:
        _check_enum("--status", status, STATUSES)
        if status in ("blocked", "waiting"):
            _require_v3(f"--status {status}")
    if scope:
        _check_enum("--scope", scope, SCOPES)
    if parent:
        _check_uuid(parent)
        _require_v3("--parent")

    params = [agent, agent, status, status, scope, scope, project, project,
              repo, repo, assignee, assignee, tag, tag, parent, parent]
    sql = build_query(SELECT_SQL, params)
    raw = psql(sql)
    if not raw:
        print("No tasks found.")
        return

    header = f"{'ID':<38} {'Agent':<10} {'Scope':<9} {'Status':<12} {'Pr':<3} {'Kind':<6} Content"
    print(header)
    print("-" * len(header))
    for line in raw.split("\n"):
        row = parse_row(line)
        if not row:
            continue
        kind = row["kind"] or "-"
        content = row["content"]
        if row["kind"] == "slice" and row["parent_id"]:
            content = f"  ↳ {content}"  # indent slices under their story
        print(f"{row['id']:<38} {row['created_by']:<10} {row['scope']:<9} "
              f"{row['status']:<12} {row['priority']:<3} {kind:<6} {content}")


def cmd_summary(story_id: str):
    """Show a story's slice-status summary (v3: tasks.task_story_summary)."""
    _check_uuid(story_id)
    _require_v3("summary")
    raw = psql("SELECT tasks.task_story_summary(?::uuid);", [story_id])
    if not raw:
        print(f"ERROR: no story with id {story_id[:8]}... (not visible or "
              f"not kind='story')", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(raw.strip().splitlines()[0])
    except (ValueError, IndexError):
        print(f"ERROR: unparseable summary for {story_id[:8]}...",
              file=sys.stderr)
        sys.exit(1)
    print(f"📚 Story {data['story_id'][:8]}... — {data['content']}")
    print(f"   status={data['status']}  priority={data['priority']}  "
          f"scope={data['scope']}  by={data['created_by']}")
    print(f"   slices: {data['total_slices']} total | "
          f"{data['completed']} done + {data['cancelled']} cancelled "
          f"({data['done_ratio']}%) | {data['active']} active "
          f"({data['in_progress']} ip, {data['paused']} paused, "
          f"{data['blocked']} blocked, {data['waiting']} waiting, "
          f"{data['pending']} pending)")


def cmd_add(content: str, agent: str | None, priority: int, project: str | None,
            repo: str | None, target: str | None, scope: str | None,
            assignee: str | None, due: str | None, tags: list[str],
            source: str | None, parent: str | None = None,
            kind: str | None = None, no_notify: bool = False,
            correlation_id: str | None = None):
    """Add a new task (v2: story/slice hierarchy + notify + bus correlation)."""
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
    if kind:
        _check_enum("--kind", kind, KINDS)
        _require_v2("--kind")
    if parent:
        _check_uuid(parent)
        _require_v2("--parent")
    if correlation_id:
        _require_v2("--correlation-id")
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
        "NULL, NULL, ?, ?::timestamptz, ?, ?, ?, ?, ?::uuid, ?, ?);",
        [new_id, content, agent, assignee, project or "hermes-cortex",
         repo, target, scope or "personal", priority, due or None,
         tags or None, source or "manual", None, session_id or None,
         parent, kind, correlation_id],
    )
    print(f"✅ Task added: {new_id[:8]}... — {content}")
    if (scope or "personal") == "fleet":
        print("⚠️  fleet task stored LOCALLY on this host only — not visible "
              "fleet-wide until transport ships (roadmap: git-backed, private repo).")
    if not no_notify and (source or "manual") != "doctor-probe":
        _notify_task(agent, kind, content, "pending", new_id,
                     parent_title=None)


def cmd_update(task_id: str, new_status: str, reason: str | None = None,
               by_correlation: str | None = None, no_notify: bool = False):
    """Update a task's status (canonical lifecycle, B-4).

    v2: --reason 'reopen' (completed→in_progress gate), --by-correlation
    (bus-command idempotency — 1 task per correlation_id), --no-notify.
    """
    _check_enum("--status", new_status, STATUSES)
    if new_status == "paused":
        _require_v2("--status paused")
    if new_status in ("blocked", "waiting"):
        _require_v3(f"--status {new_status}")
    if by_correlation:
        _require_v2("--by-correlation")
        # Partial unique index (source='inbox' AND correlation_id NOT NULL)
        # guarantees at most one row. RLS filters to visible rows.
        found = psql(
            "SELECT id FROM tasks.tasks WHERE source = 'inbox' "
            "AND correlation_id = ? LIMIT 1;",
            [by_correlation],
        )
        if not found:
            print(f"ERROR: no inbox task with correlation_id "
                  f"'{by_correlation}' (RLS-visible)", file=sys.stderr)
            sys.exit(1)
        task_id = found.split("\n")[0]
    else:
        _check_uuid(task_id)

    if reason:
        _require_v2("--reason")
        # Set the session GUC that the transition/event triggers read.
        # Multi-statement via stdin: GUC + upsert in one session.
        psql(
            "SELECT set_config('tasks.transition_reason', ?, false);\n"
            "SELECT tasks.task_upsert(?::uuid, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, NULL);",
            [reason, task_id, new_status],
        )
    else:
        psql(
            "SELECT tasks.task_upsert(?::uuid, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, NULL);",
            [task_id, new_status],
        )
    print(f"✅ Task {task_id[:8]}... → {new_status}"
          + (f" (reason={reason})" if reason else "")
          + (f" [corr={by_correlation[:12]}…]" if by_correlation else ""))
    if not no_notify:
        # Fetch row for the notify message (best-effort)
        try:
            row_sql = build_query(
                f"SELECT {SELECT_COLS} FROM tasks.tasks WHERE id = ?;",
                [task_id])
            row_raw = psql(row_sql)
            row = parse_row(row_raw.split("\n")[0]) if row_raw else None
            if row:
                parent_title = None
                if row["parent_id"]:
                    p_raw = psql(build_query(
                        "SELECT content FROM tasks.tasks WHERE id = ?;",
                        [row["parent_id"]]))
                    parent_title = p_raw.split("\n")[0] if p_raw else None
                _notify_task(row["created_by"], row["kind"], row["content"],
                             new_status, task_id, parent_title)
        except SystemExit:
            pass  # read-only notify failure never blocks the update


def cmd_switch(target_id: str, no_notify: bool = False):
    """Pause the current in_progress task (reason='switch') and resume target.

    v2 (M-8): one command, atomic DB transaction, two events.
    Edge cases: target == current → no-op; no current in_progress → just
    resume target; target is a story → rejected.
    """
    _require_v2("switch")
    _check_uuid(target_id)

    # Current in_progress = latest status_changed_at for this profile
    current_raw = psql(
        "SELECT id FROM tasks.tasks WHERE created_by = ? AND status = "
        "'in_progress' ORDER BY status_changed_at DESC LIMIT 1;",
        [PROFILE],
    )
    current_id = current_raw.split("\n")[0] if current_raw else ""

    # Target checks
    target_raw = psql(
        f"SELECT {SELECT_COLS} FROM tasks.tasks WHERE id = ?;", [target_id])
    if not target_raw:
        print(f"ERROR: target task {target_id[:8]}... not found or not visible",
              file=sys.stderr)
        sys.exit(1)
    target_row = parse_row(target_raw.split("\n")[0])
    if target_row is None:
        print("ERROR: target row unparseable", file=sys.stderr)
        sys.exit(1)
    if target_row["kind"] == "story":
        print("ERROR: cannot switch to a story — resume a slice instead",
              file=sys.stderr)
        sys.exit(2)

    if current_id and current_id == target_id:
        print(f"ℹ️  Task {target_id[:8]}... is already the active task — no-op")
        return

    # Atomic: GUC + pause current + resume target in ONE session/transaction.
    if current_id:
        psql(
            "SELECT set_config('tasks.transition_reason', 'switch', false);\n"
            "SELECT tasks.task_upsert(?::uuid, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, 'paused', NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, NULL, NULL);\n"
            "SELECT tasks.task_upsert(?::uuid, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, 'in_progress', NULL, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, NULL, NULL, NULL);",
            [current_id, target_id],
        )
        print(f"✅ Switched: paused {current_id[:8]}... → resumed {target_id[:8]}...")
        if not no_notify:
            _notify_task(PROFILE, target_row["kind"], target_row["content"],
                         "in_progress", target_id)
    else:
        # No active task — just resume the target (pending→in_progress or
        # paused→in_progress are both legal transitions).
        psql(
            "SELECT tasks.task_upsert(?::uuid, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, 'in_progress', NULL, NULL, NULL, NULL, NULL, NULL, "
            "NULL, NULL, NULL, NULL, NULL);",
            [target_id],
        )
        print(f"✅ Resumed {target_id[:8]}... (no other task was active)")
        if not no_notify:
            _notify_task(PROFILE, target_row["kind"], target_row["content"],
                         "in_progress", target_id)


def cmd_pending():
    """Print pending/in_progress/paused tasks as JSON for session restore.

    v2 (M-9/R-4): paused rows are included with status='paused' (surfaced,
    never auto-resumed by restore); inbox-derived rows carry
    'untrusted': true so restore skips them unless --include-inbox.
    v3 (M-7): blocked/waiting rows are surfaced the same way — restore keeps
    their status (never auto-resumed into in_progress).
    """
    raw = psql(build_query(
        f"SELECT {SELECT_COLS} FROM tasks.tasks t "
        "WHERE t.status IN ('pending','in_progress','paused','blocked','waiting') "
        "ORDER BY t.priority DESC, t.created_at ASC LIMIT 500;", None))
    items = []
    for line in raw.split("\n"):
        row = parse_row(line)
        if not row or row["status"] not in ("pending", "in_progress", "paused",
                                            "blocked", "waiting"):
            continue
        item = {
            "id": row["id"], "content": row["content"],
            "agent_name": row["created_by"], "status": row["status"],
            "session_id": row["session_id"], "priority": row["priority"],
            "project": row["project"], "repo": row["repo"], "scope": row["scope"],
            "kind": row["kind"], "parent_id": row["parent_id"],
            "untrusted": row["source"] == "inbox",
        }
        items.append(item)
    print(json.dumps(items, indent=2))


def cmd_restore(json_file: str, include_inbox: bool = False):
    """Bulk-restore tasks from a JSON file (session start).

    v2 (R-4): skips 'untrusted' (inbox-derived) rows unless --include-inbox;
    paused rows restore as paused — never auto-resumed (M-9).
    """
    if not os.path.exists(json_file):
        print(f"No restore file: {json_file} — starting fresh.")
        return
    with open(json_file) as f:
        items = json.load(f)
    if not items:
        print("No pending tasks to restore.")
        return

    count = 0
    skipped = 0
    for item in items:
        if item.get("untrusted") and not include_inbox:
            skipped += 1
            continue
        _check_uuid(item["id"])
        status = item.get("status", "pending")
        if status not in STATUSES:
            status = "pending"
        psql(
            "SELECT tasks.task_upsert(?::uuid, ?, ?, NULL, ?, NULL, NULL, ?, ?, "
            "NULL, NULL, ?, NULL, NULL, ?, NULL, ?, ?::uuid, ?, NULL);",
            [item["id"], item["content"], item.get("agent_name", PROFILE),
             item.get("project", "hermes-cortex"),
             item.get("scope", "personal"), status,
             item.get("priority", 0), item.get("source", "session"),
             item.get("session_id"), item.get("parent_id"),
             item.get("kind")],
        )
        count += 1
    msg = f"✅ Restored {count} task(s) from {json_file}"
    if skipped:
        msg += f" (skipped {skipped} untrusted inbox-derived row(s) — use --include-inbox to force)"
    print(msg)


def cmd_save_end():
    """Session-end: archive completed/cancelled, keep pending."""
    result = psql("SELECT tasks.task_archive_old(?);", [PROFILE])
    archived = result.strip()
    print(f"Archived {archived} completed/cancelled task(s) for {PROFILE}.")

    pending = psql(
        f"SELECT count(*) FROM tasks.tasks WHERE status IN "
        f"('pending','in_progress','paused') AND created_by = ?;",
        [PROFILE],
    )
    if pending and int(pending) > 0:
        print(f"⚠️  {pending} task(s) remain for next session.")


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

    def _has(name: str) -> bool:
        return name in sys.argv

    if command == "list":
        cmd_list(
            _flag("--agent"), _flag("--status"), _flag("--project"),
            _flag("--scope"), _flag("--repo"), _flag("--assignee"),
            _flag("--tag"), _flag("--due-before"), _flag("--parent"),
        )

    elif command == "summary":
        if len(sys.argv) < 3:
            print("ERROR: Usage: task-db.py summary <story-id>",
                  file=sys.stderr)
            sys.exit(1)
        cmd_summary(sys.argv[2])

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
            _flag("--source"), _flag("--parent"), _flag("--kind"),
            _has("--no-notify"), _flag("--correlation-id"),
        )

    elif command == "update":
        by_corr = _flag("--by-correlation")
        new_status = _flag("--status")
        if not new_status:
            print("ERROR: --status requires a value", file=sys.stderr)
            sys.exit(1)
        if not by_corr and (len(sys.argv) < 3 or sys.argv[2].startswith("--")):
            print("ERROR: Usage: task-db.py update <id> --status <new-status> "
                  "(or --by-correlation <corr> --status <new-status>)",
                  file=sys.stderr)
            sys.exit(1)
        cmd_update(sys.argv[2] if not by_corr else "",
                   new_status, _flag("--reason"), by_corr,
                   _has("--no-notify"))

    elif command == "switch":
        if len(sys.argv) < 3:
            print("ERROR: Usage: task-db.py switch <target-id>", file=sys.stderr)
            sys.exit(1)
        cmd_switch(sys.argv[2], _has("--no-notify"))

    elif command == "pending":
        cmd_pending()

    elif command == "restore":
        include_inbox = _has("--include-inbox")
        cmd_restore(sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "/dev/stdin",
                    include_inbox)

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
