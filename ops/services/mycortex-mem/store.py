#!/usr/bin/env python3
"""store.py — ONE store for memory and session (`mycortex_mem`).

Why one module: memory and session are two views of the same store. `sessions`
already keys a conversation, `messages` already holds its history (with an FTS
index), `conclusions`/`profiles` are what memory distilled out of it. Splitting
them into two services would mean two connections, two identity resolutions and
two slowly-diverging opinions about what a session is.

Design: docs/design/cortex-memory-session-mcp.md

**No Hermes imports.** The plugin (`plugins/mycortex-mem/`) reaches this store
through a provider registered in the Hermes process; this module is the same
store with no harness coupling, so an MCP server — and therefore Pi, Claude
Code, or any other harness — can use it. The plugin can be migrated onto this
module later, which is what makes it deletable rather than a rewrite.

Everything is psql-over-subprocess: the Linux path runs psql inside the
`mycortex-postgres` container via `sg docker -c`, the macOS path runs psql
directly with a 0600 PGPASSFILE. Roles are least-privilege
(`mycortex_mem_reader` / `mycortex_mem_writer`).

Fail-open by contract: `available()` returning False means "memory unavailable,
carry on", never an exception that kills a harness at start-up.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any, Optional

# ── Constants (mirror plugins/mycortex-mem/__init__.py — one source of truth
#    for the connection shape; do not invent a second path) ──────
_DEFAULT_PORT = 15432
_DEFAULT_DB = "mycortex"
_DEFAULT_CONTAINER = "mycortex-postgres"
_READER = "mycortex_mem_reader"
_WRITER = "mycortex_mem_writer"

_MAX_SESSION_KEY = 200


class StoreUnavailable(RuntimeError):
    """The store cannot be reached. Callers fail open, never crash."""


def _lit(value: Any) -> str:
    """Quote a Python value as a safe SQL literal.

    Hand-rolled rather than parameterised because the seam is psql-over-stdin
    (no driver); the escape is the standard doubling of single quotes. Never
    interpolate an unescaped value into SQL.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _json_lit(value: Any) -> str:
    """A JSONB literal (list/dict → jsonb). Always cast, never implicit."""
    return _lit(json.dumps(value if value is not None else [])) + "::jsonb"


class PgConnection:
    """Thin psql-based connection seam. Testable via injection."""

    def __init__(self, db_name: str = _DEFAULT_DB, port: int = _DEFAULT_PORT,
                 container: str = _DEFAULT_CONTAINER):
        self._db_name = db_name
        self._port = port
        self._container = container
        self._is_macos = os.uname().sysname == "Darwin"

    def _cmd(self, role: str) -> tuple[list[str], dict]:
        if self._is_macos:
            pw = os.environ.get("MYCORTEX_MEM_PASSWORD", "")
            pgpass = f"localhost:{self._port}:{self._db_name}:{role}:{pw}"
            f = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pgpass")
            f.write(pgpass + "\n")
            f.close()
            os.chmod(f.name, 0o600)
            return (
                ["psql", "-h", "localhost", "-p", str(self._port), "-U", role,
                 "-d", self._db_name, "-v", "ON_ERROR_STOP=1", "-t", "-A"],
                {"PGPASSFILE": f.name},
            )
        return (
            ["sg", "docker", "-c",
             f"docker exec -i {self._container} psql -U {role} -d {self._db_name} "
             f"-v ON_ERROR_STOP=1 -t -A"],
            {},
        )

    def _run(self, sql: str, role: str, timeout: int) -> str:
        cmd, env = self._cmd(role)
        try:
            r = subprocess.run(cmd, input=sql, capture_output=True, text=True,
                               timeout=timeout, env={**os.environ, **env})
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise StoreUnavailable(f"psql unavailable: {exc}") from exc
        if r.returncode != 0:
            raise StoreUnavailable(f"psql error: {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout.strip()

    def run_sql(self, sql: str, role: str = _WRITER, timeout: int = 10) -> str:
        return self._run(sql, role, timeout)

    def query(self, sql: str, role: str = _READER, timeout: int = 10) -> list[list[str]]:
        out = self._run(sql, role, timeout)
        if not out:
            return []
        return [row.split("|") for row in out.split("\n")]

    def scalar(self, sql: str, role: str = _READER, default: str = "",
               timeout: int = 10) -> str:
        rows = self.query(sql, role=role, timeout=timeout)
        if rows and rows[0]:
            return rows[0][0]
        return default

    def row(self, sql: str, role: str = _READER) -> Optional[list[str]]:
        rows = self.query(sql, role=role)
        return rows[0] if rows else None

    def available(self, timeout: int = 3) -> bool:
        """True when the store answers. Never raises — fail-open contract."""
        try:
            self.scalar("SELECT 1;", timeout=timeout)
            return True
        except Exception:
            return False


# ── Memory half ───────────────────────────────────────────────────

class MemoryStore:
    """Peer card, durable conclusions, message history search."""

    def __init__(self, pg: PgConnection):
        self.pg = pg

    def peer_id(self, peer_name: str, peer_type: str = "user") -> str:
        """Resolve (creating if needed) a peer row → id.

        Identity resolution lives in ONE place so a session and a peer card can
        never disagree about who a conversation is with.
        """
        self.pg.run_sql(
            "INSERT INTO mycortex_mem.peers (workspace, peer_name, peer_type) "
            f"VALUES ('default', {_lit(peer_name)}, {_lit(peer_type)}) "
            "ON CONFLICT (workspace, peer_name) DO NOTHING;"
        )
        return self.pg.scalar(
            "SELECT id::text FROM mycortex_mem.peers "
            f"WHERE workspace='default' AND peer_name={_lit(peer_name)};"
        )

    def get_card(self, peer_name: str = "user") -> list[str]:
        raw = self.pg.scalar(
            "SELECT card::text FROM mycortex_mem.profiles p "
            "JOIN mycortex_mem.peers pe ON pe.id = p.peer_id "
            f"WHERE pe.peer_name = {_lit(peer_name)};"
        )
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        return data if isinstance(data, list) else []

    def set_card(self, card: list[str], peer_name: str = "user") -> None:
        peer = self.peer_id(peer_name)
        self.pg.run_sql(
            "INSERT INTO mycortex_mem.profiles (peer_id, card) "
            f"VALUES ({_lit(peer)}::uuid, {_json_lit(card)}) "
            f"ON CONFLICT (peer_id) DO UPDATE SET card = {_json_lit(card)}, "
            "updated_at = now();"
        )

    def conclusions(self, peer_name: str = "user", limit: int = 20) -> list[dict]:
        rows = self.pg.query(
            "SELECT c.id::text, c.fact, c.confidence, c.source "
            "FROM mycortex_mem.conclusions c "
            "JOIN mycortex_mem.peers pe ON pe.id = c.peer_id "
            f"WHERE pe.peer_name = {_lit(peer_name)} AND NOT c.archived "
            f"ORDER BY c.created_at DESC LIMIT {int(limit)};"
        )
        return [{"id": r[0], "fact": r[1], "confidence": r[2], "source": r[3]}
                for r in rows if len(r) >= 4]

    def add_conclusion(self, fact: str, peer_name: str = "user",
                       source: str = "agent") -> None:
        peer = self.peer_id(peer_name)
        self.pg.run_sql(
            "INSERT INTO mycortex_mem.conclusions (peer_id, fact, source) "
            f"VALUES ({_lit(peer)}::uuid, {_lit(fact)}, {_lit(source)});"
        )

    def delete_conclusion(self, conclusion_id: str) -> None:
        self.pg.run_sql(
            "UPDATE mycortex_mem.conclusions SET archived = TRUE "
            f"WHERE id = {_lit(conclusion_id)}::uuid;"
        )

    def search_messages(self, query: str, limit: int = 10) -> list[dict]:
        """Full-text search over stored message history (the same `messages`
        table session history lives in — one store, one ranking path)."""
        rows = self.pg.query(
            "SELECT m.role, substring(m.content, 1, 500), m.created_at::text "
            "FROM mycortex_mem.messages m "
            "WHERE to_tsvector('english', coalesce(m.content, '')) "
            f"@@ plainto_tsquery('english', {_lit(query)}) "
            f"ORDER BY m.created_at DESC LIMIT {int(limit)};"
        )
        return [{"role": r[0], "excerpt": r[1], "at": r[2]}
                for r in rows if len(r) >= 3]

    def recent_messages(self, limit: int = 5) -> list[dict]:
        rows = self.pg.query(
            "SELECT role, substring(content, 1, 200), created_at::text "
            f"FROM mycortex_mem.messages ORDER BY created_at DESC LIMIT {int(limit)};"
        )
        return [{"role": r[0], "excerpt": r[1], "at": r[2]}
                for r in rows if len(r) >= 3]


# ── Session half ──────────────────────────────────────────────────

class SessionStore:
    """Checkpoint / restore / list / search over the same store."""

    def __init__(self, pg: PgConnection, mem: Optional[MemoryStore] = None):
        self.pg = pg
        self.mem = mem or MemoryStore(pg)

    @staticmethod
    def session_key(harness: str, repo: str = "", branch: str = "") -> str:
        """Derived, explicit session identity: `harness:repo:branch`.

        Never "latest" — a caller that cannot name its session must not
        silently resume someone else's. Bounded so a pathological path cannot
        overflow the column.
        """
        parts = [p.strip() for p in (harness, repo, branch) if p and p.strip()]
        return ":".join(parts)[:_MAX_SESSION_KEY]

    def session_id(self, harness: str, repo: str = "", branch: str = "",
                   create: bool = True) -> str:
        key = self.session_key(harness, repo, branch)
        if create:
            self.pg.run_sql(
                "INSERT INTO mycortex_mem.sessions (session_key) "
                f"VALUES ({_lit(key)}) ON CONFLICT (session_key) DO NOTHING;"
            )
        return self.pg.scalar(
            f"SELECT id::text FROM mycortex_mem.sessions WHERE session_key = {_lit(key)};"
        )

    def checkpoint(self, harness: str, repo: str = "", branch: str = "",
                   done: Optional[list] = None, pending: Optional[list] = None,
                   blockers: Optional[list] = None, decisions: Optional[list] = None,
                   notes: str = "") -> str:
        """Append a checkpoint. Append-only by design: concurrent writers cannot
        corrupt each other's history, and the latest row is the restore point."""
        sid = self.session_id(harness, repo, branch)
        if not sid:
            raise StoreUnavailable("could not resolve a session id")
        self.pg.run_sql(
            "INSERT INTO mycortex_mem.checkpoints "
            "(session_id, harness, repo, branch, done, pending, blockers, decisions, notes) "
            f"VALUES ({_lit(sid)}::uuid, {_lit(harness)}, {_lit(repo)}, {_lit(branch)}, "
            f"{_json_lit(done or [])}, {_json_lit(pending or [])}, "
            f"{_json_lit(blockers or [])}, {_json_lit(decisions or [])}, {_lit(notes)});"
        )
        self.pg.run_sql(
            "UPDATE mycortex_mem.sessions SET updated_at = now(), ended_at = NULL "
            f"WHERE id = {_lit(sid)}::uuid;"
        )
        return sid

    def latest(self, harness: str, repo: str = "", branch: str = "") -> Optional[dict]:
        """The most recent checkpoint for a session — facts, never a transcript."""
        row = self.pg.row(
            "SELECT c.id::text, c.done::text, c.pending::text, c.blockers::text, "
            "c.decisions::text, coalesce(c.notes, ''), c.created_at::text, s.session_key "
            "FROM mycortex_mem.checkpoints c "
            "JOIN mycortex_mem.sessions s ON s.id = c.session_id "
            f"WHERE s.session_key = {_lit(self.session_key(harness, repo, branch))} "
            "ORDER BY c.created_at DESC LIMIT 1;"
        )
        return self._row_to_checkpoint(row)

    @staticmethod
    def _row_to_checkpoint(row: Optional[list[str]]) -> Optional[dict]:
        if not row or len(row) < 8:
            return None

        def _load(raw: str) -> list:
            try:
                v = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
            return v if isinstance(v, list) else []

        return {
            "checkpoint_id": row[0], "done": _load(row[1]), "pending": _load(row[2]),
            "blockers": _load(row[3]), "decisions": _load(row[4]), "notes": row[5],
            "at": row[6], "session_key": row[7],
        }

    # ── Tool events (HC's own session record — NOT Hermes's state.db) ──
    #
    # The pre-commit reflexion gate needs to know "did this session load skill
    # X?". It used to ask ~/.hermes/state.db, which is HERMES-owned: fragile to
    # its schema, and structurally unsatisfiable for a harness with no Hermes
    # (Pi, aider, CI). Recording it here makes the gate harness-agnostic and
    # removes the incumbent dependency — no fallback, by design.

    def record_tool_event(self, harness: str, tool_name: str, content,
                          role: str = "tool", repo: str = "", branch: str = "",
                          session_key: Optional[str] = None) -> None:
        """Record one tool invocation for the current session.

        The session row is ENSURED first (idempotent), then the event is written
        by subquery. Both halves matter, and the first cut only had the second:

          - recording must never FAIL because a session row is absent, and
          - the event must never be UNROUTABLE because the row is absent.

        Writing without the row stores `session_id NULL`, which the gate can
        never match — "never fails" achieved by making the event useless.
        Measured on the first cut: `loaded_skill()` returned False for an event
        that had, in fact, been written successfully.
        """
        key = session_key or self.session_key(harness, repo, branch)
        self.pg.run_sql(
            "INSERT INTO mycortex_mem.sessions (session_key) "
            f"VALUES ({_lit(key)}) ON CONFLICT (session_key) DO NOTHING;",
            role=_WRITER,
        )
        payload = content if isinstance(content, str) else json.dumps(content)
        self.pg.run_sql(
            "INSERT INTO mycortex_mem.tool_events "
            "(session_id, harness, tool_name, role, content) VALUES ("
            f"(SELECT id FROM mycortex_mem.sessions WHERE session_key = {_lit(key)}), "
            f"{_lit(harness)}, {_lit(tool_name)}, {_lit(role)}, "
            f"{_lit(payload)}::jsonb);",
            role=_WRITER,
        )

    def loaded_skill(self, skill: str, harness: str, repo: str = "",
                     branch: str = "", session_key: Optional[str] = None) -> bool:
        """Did this session load `skill`? The gate's question, answered from HC's
        own store. Same semantics as Hermes's: tool_name='skill_view', role='tool',
        and a payload naming the skill — so the gate's question is unchanged while
        the dependency is gone."""
        key = session_key or self.session_key(harness, repo, branch)
        row = self.pg.row(
            "SELECT 1 FROM mycortex_mem.tool_events e "
            "JOIN mycortex_mem.sessions s ON s.id = e.session_id "
            f"WHERE s.session_key = {_lit(key)} AND e.tool_name = 'skill_view' "
            f"AND e.role = 'tool' AND e.content_text_tsv @@ "
            f"plainto_tsquery('simple', {_lit(skill)}) LIMIT 1;"
        )
        return row is not None

    def list_sessions(self, limit: int = 10) -> list[dict]:
        rows = self.pg.query(
            "SELECT s.session_key, s.started_at::text, "
            "coalesce(s.ended_at::text, ''), s.message_count, "
            "(SELECT count(*) FROM mycortex_mem.checkpoints c WHERE c.session_id = s.id) "
            "FROM mycortex_mem.sessions s "
            f"ORDER BY s.updated_at DESC LIMIT {int(limit)};"
        )
        return [{"session_key": r[0], "started_at": r[1], "ended_at": r[2],
                 "message_count": r[3], "checkpoints": r[4]}
                for r in rows if len(r) >= 5]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search structured session state AND message history in one call.

        One query surface over one store — the memory family and the session
        family do not get two indexes that can disagree.
        """
        out: list[dict] = []
        rows = self.pg.query(
            "SELECT s.session_key, c.decisions::text, c.blockers::text, "
            "coalesce(c.notes, ''), c.created_at::text "
            "FROM mycortex_mem.checkpoints c "
            "JOIN mycortex_mem.sessions s ON s.id = c.session_id "
            "WHERE to_tsvector('english', "
            "        coalesce(c.notes,'') || ' ' || coalesce(c.done::text,'') || ' ' || "
            "        coalesce(c.pending::text,'') || ' ' || coalesce(c.blockers::text,'') || ' ' || "
            "        coalesce(c.decisions::text,'')) "
            f"      @@ plainto_tsquery('english', {_lit(query)}) "
            f"ORDER BY c.created_at DESC LIMIT {int(limit)};"
        )
        for r in rows:
            if len(r) >= 5:
                out.append({"kind": "checkpoint", "session_key": r[0],
                            "decisions": r[1], "blockers": r[2], "notes": r[3], "at": r[4]})
        for m in self.mem.search_messages(query, limit=limit):
            out.append({"kind": "message", **m})
        return out

    def note(self, harness: str, text: str, repo: str = "", branch: str = "") -> None:
        """Append a durable progress line mid-session (folded into the next
        restore's notes rather than a separate event log)."""
        sid = self.session_id(harness, repo, branch)
        if not sid:
            raise StoreUnavailable("could not resolve a session id")
        self.pg.run_sql(
            "INSERT INTO mycortex_mem.messages (session_id, peer_id, role, content) "
            "SELECT s.id, p.id, 'note', " + _lit(text[:5000]) + " "
            "FROM mycortex_mem.sessions s "
            "JOIN mycortex_mem.peers p ON p.peer_name = 'ai' "
            f"WHERE s.id = {_lit(sid)}::uuid "
            "ON CONFLICT DO NOTHING;"
        )

    def close(self, harness: str, repo: str = "", branch: str = "",
              promote_decisions: bool = False) -> Optional[dict]:
        """Final snapshot + end the session.

        `promote_decisions` is the mix/match seam: the durable facts recorded at
        a checkpoint are exactly what the memory family stores, so they can be
        carried across instead of being lost in a session blob.
        """
        snap = self.latest(harness, repo, branch)
        sid = self.session_id(harness, repo, branch, create=False)
        if sid:
            self.pg.run_sql(
                f"UPDATE mycortex_mem.sessions SET ended_at = now(), "
                f"updated_at = now() WHERE id = {_lit(sid)}::uuid;"
            )
        if promote_decisions and snap:
            for fact in (snap.get("decisions") or []):
                self.mem.add_conclusion(str(fact), source="session")
        return snap


class Store:
    """One store, two views. This is the object an MCP server (or the plugin,
    once migrated) holds — memory and session resolving against the same
    connection and the same identity model."""

    def __init__(self, pg: Optional[PgConnection] = None):
        self.pg = pg or PgConnection()
        self.memory = MemoryStore(self.pg)
        self.sessions = SessionStore(self.pg, self.memory)

    def available(self) -> bool:
        return self.pg.available()
