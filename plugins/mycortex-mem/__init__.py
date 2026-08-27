#!/usr/bin/env python3
"""mycortex-mem memory plugin — MemoryProvider for local Postgres memory (Honcho replacement).

Provides cross-session user modeling with dialectic Q&A, semantic search,
peer cards, and persistent conclusions via the mycortex-mem schema on
mycortex-postgres.

Five tools (mem_profile, mem_search, mem_context, mem_reasoning, mem_conclude)
exposed through the MemoryProvider interface.

Design:
  - Deep module behind MemoryProvider ABC (small interface, lots of implementation)
  - Postgres backend on mycortex-postgres (:15432), schema mycortex_mem
  - Peer model: each workspace has peers (user, ai)
  - Auto-injection cadence with configurable frequency
  - Background prefetch + synchronous turn sync
  - Dialectic-style reasoning via internal LLM (auxiliary_client.call_llm)

Configuration (config.yaml):
  memory:
    provider: mycortex-mem
    mycortex-mem:
      recall_mode: hybrid        # hybrid | context | tools
      injection_frequency: every-turn  # every-turn | first-turn
      context_cadence: 1          # min turns between context fetches
      dialectic_cadence: 2        # min turns between dialectic reasoning
      dialectic_depth: 1          # 1-3 rounds of self-audit synthesis
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.memory_provider import INDICATOR_GLYPH, MemoryProvider, RecallStatus, is_trivial_prompt
from tools.registry import tool_error

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────
_DEFAULT_PORT = 15432
_DEFAULT_DB = "mycortex"
_DEFAULT_CONTAINER = "mycortex-postgres"
_MIN_QUERY_LEN = 10
_PREFETCH_TIMEOUT = 5
_SYNC_TIMEOUT = 10
_REASONING_TIMEOUT = 60
_MAX_CARD_FACTS = 50

_LEVEL_ORDER = {"minimal": 0, "low": 1, "medium": 2, "high": 3, "max": 4}


class _PgConnection:
    """Thin psql-based Postgres connection seam. Testable via injection."""

    def init(self, db_name: str = _DEFAULT_DB):
        self._db_name = db_name
        self._is_macos = os.uname().sysname == "Darwin"

    def _cmd(self, role: str) -> tuple[list[str], dict]:
        if self._is_macos:
            pw = os.environ.get("MYCORTEX_MEM_PASSWORD", "")
            pgpass = f"localhost:{_DEFAULT_PORT}:{self._db_name}:{role}:{pw}"
            import tempfile
            f = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pgpass")
            f.write(pgpass + "\n")
            f.close()
            os.chmod(f.name, 0o600)
            return ["psql", "-h", "localhost", "-p", str(_DEFAULT_PORT), "-U", role, "-d", self._db_name, "-v", "ON_ERROR_STOP=1", "-t", "-A"], {"PGPASSFILE": f.name}
        else:
            return [
                "sg", "docker", "-c",
                f"docker exec -i {_DEFAULT_CONTAINER} psql -U {role} -d {self._db_name} -v ON_ERROR_STOP=1 -t -A"
            ], {}

    def run_sql(self, sql: str, role: str = "mycortex_mem_writer", timeout: int = 10) -> str:
        cmd, env = self._cmd(role)
        r = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=timeout, env={**os.environ, **env})
        if r.returncode != 0:
            raise RuntimeError(f"psql error: {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout.strip()

    def query(self, sql: str, role: str = "mycortex_mem_reader", timeout: int = 10) -> list[list[str]]:
        cmd, env = self._cmd(role)
        r = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=timeout, env={**os.environ, **env})
        if r.returncode != 0:
            raise RuntimeError(f"psql error: {r.stderr.strip()}")
        out = r.stdout.strip()
        if not out:
            return []
        return [row.split("|") for row in out.split("\n")]

    def scalar(self, sql: str, role: str = "mycortex_mem_reader", default: str = "", timeout: int = 10) -> str:
        rows = self.query(sql, role=role, timeout=timeout)
        if rows and rows[0]:
            return rows[0][0]
        return default

    def row(self, sql: str, role: str = "mycortex_mem_reader") -> Optional[list[str]]:
        rows = self.query(sql, role=role)
        return rows[0] if rows else None


# ── Tool schemas ──────────────────────────────────────────────
PROFILE_SCHEMA = {
    "name": "mem_profile",
    "description": "Read or write a peer's CARD — a short, curated list of standing facts about that peer (name, role, preferences, communication style, recurring patterns). This is the cheapest call: no LLM, just the current card. Pass card as a list of fact strings to overwrite; omit card to read. Related: mem_context for full snapshot, mem_search for past facts, mem_reasoning for synthesized answers.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {"type": "string", "description": "Peer name: 'user' (default) or 'ai'.", "default": "user"},
            "card": {"type": "array", "items": {"type": "string"}, "description": "New card fact list. Omit to read current card."},
        },
        "required": [],
    },
}

SEARCH_SCHEMA = {
    "name": "mem_search",
    "description": "Hybrid search over a peer's message history across all past sessions. Returns ranked raw message excerpts (what was literally said), no LLM synthesis. Cheaper than mem_reasoning. Use to recall specific past facts — 'what did we decide about X', 'what was the config we settled on'. For nuanced questions needing synthesis, use mem_reasoning.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for — topic, keyword, or natural-language description."},
            "peer": {"type": "string", "description": "Whose history to search: 'user' (default) or 'ai'.", "default": "user"},
            "limit": {"type": "integer", "description": "Max results (default 5, max 20).", "default": 5},
        },
        "required": ["query"],
    },
}

CONTEXT_SCHEMA = {
    "name": "mem_context",
    "description": "Retrieve the full standing snapshot for the current session — session summary, peer card, and recent activity — in one call. No query, no LLM. Use to orient yourself on what's known about this conversation and peers. For specific facts use mem_search; for synthesized answers use mem_reasoning.",
    "parameters": {
        "type": "object",
        "properties": {
            "peer": {"type": "string", "description": "Peer name: 'user' (default) or 'ai'.", "default": "user"},
        },
        "required": [],
    },
}

REASONING_SCHEMA = {
    "name": "mem_reasoning",
    "description": "Ask a natural-language question about a peer and get back a SYNTHESIZED answer. This runs an LLM call: it searches messages and conclusions, reasons over them, and writes a prose answer — the slowest and most expensive call. Use for nuanced questions ('how does this person prefer to receive feedback?', 'what patterns do you see in their requests?'). For specific past facts, prefer mem_search (cheap, raw excerpts). Pass reasoning_level to control depth: minimal (fast/cheap), low (default), medium, high, max (deep/expensive).",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "A natural language question."},
            "peer": {"type": "string", "description": "Peer to query: 'user' (default) or 'ai'.", "default": "user"},
            "reasoning_level": {"type": "string", "enum": ["minimal", "low", "medium", "high", "max"], "description": "Reasoning depth. Low is the default."},
        },
        "required": ["query"],
    },
}

CONCLUDE_SCHEMA = {
    "name": "mem_conclude",
    "description": "Write or delete persistent CONCLUSIONS about a peer. Pass conclusion text to create a new fact. Pass delete_id (UUID) to remove a conclusion. Pass list with optional query to search existing conclusions. Use to record stable preferences, corrections, or standing constraints.",
    "parameters": {
        "type": "object",
        "properties": {
            "conclusion": {"type": "string", "description": "Fact to remember about the peer."},
            "delete_id": {"type": "string", "description": "UUID of a conclusion to delete (from list output)."},
            "list": {"type": "boolean", "description": "Set true to list/search existing conclusions."},
            "query": {"type": "string", "description": "Optional search term when listing conclusions."},
            "peer": {"type": "string", "description": "Peer: 'user' (default) or 'ai'.", "default": "user"},
        },
        "required": [],
    },
}


class MycortexMemMemoryProvider(MemoryProvider):
    """Postgres-based persistent memory (Honcho replacement)."""

    def __init__(self, query_rewriter: Optional[Callable[[str], str]] = None):
        self._pg: Optional[_PgConnection] = None
        self._workspace = "hermes"
        self._session_key = ""
        self._user_peer_id = ""
        self._ai_peer_id = ""
        self._session_id = ""
        self._recall_mode = "hybrid"
        self._injection_frequency = "every-turn"
        self._context_cadence = 1
        self._dialectic_cadence = 2
        self._dialectic_depth = 1
        self._query_rewriter = query_rewriter
        self._turn_count = 0
        self._last_context_turn = -999
        self._last_dialectic_turn = -999
        self._prefetch_result = ""
        self._prefetch_lock = threading.Lock()
        self._prefetch_thread: Optional[threading.Thread] = None
        self._sync_thread: Optional[threading.Thread] = None
        self._cron_skipped = False

    @property
    def name(self) -> str:
        return "mycortex-mem"

    def is_available(self) -> bool:
        try:
            pg = _PgConnection()
            pg.init()
            pg.scalar("SELECT 1;", role="mycortex_mem_reader", timeout=3)
            return True
        except Exception:
            return False

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {"key": "recall_mode", "description": "hybrid (default), context, or tools", "default": "hybrid", "choices": ["hybrid", "context", "tools"]},
            {"key": "injection_frequency", "description": "every-turn or first-turn", "default": "every-turn", "choices": ["every-turn", "first-turn"]},
            {"key": "context_cadence", "description": "Min turns between context fetches (1-10)", "default": 1, "type": "integer"},
            {"key": "dialectic_cadence", "description": "Min turns between reasoning calls (1-10)", "default": 2, "type": "integer"},
            {"key": "dialectic_depth", "description": "Reasoning rounds per synthesis (1-3)", "default": 1, "type": "integer"},
        ]

    def initialize(self, session_id: str, **kwargs) -> None:
        agent_context = kwargs.get("agent_context", "")
        platform = kwargs.get("platform", "cli")
        if agent_context in {"cron", "flush"} or platform == "cron":
            logger.debug("mycortex-mem skipped: cron/flush context")
            self._cron_skipped = True
            return
        self._pg = _PgConnection()
        self._pg.init()
        self._workspace = kwargs.get("agent_workspace", "hermes")
        self._session_key = session_id or "hermes-default"
        self._session_id = session_id or ""
        self._load_config()
        self._ensure_peer("user", "user")
        ai_peer_name = kwargs.get("agent_identity", "ai")
        self._ensure_peer(ai_peer_name, "ai")
        self._user_peer_id = self._resolve_peer_id("user")
        self._ai_peer_id = self._resolve_peer_id(ai_peer_name)
        self._ensure_session()

    def _load_config(self) -> None:
        try:
            from hermes_cli.config import load_config
            cfg = load_config()
            mem_cfg = cfg.get("memory", {}).get("mycortex-mem", {}) or {}
            if isinstance(mem_cfg, dict):
                self._recall_mode = mem_cfg.get("recall_mode", self._recall_mode)
                self._injection_frequency = mem_cfg.get("injection_frequency", self._injection_frequency)
                self._context_cadence = int(mem_cfg.get("context_cadence", self._context_cadence))
                self._dialectic_cadence = int(mem_cfg.get("dialectic_cadence", self._dialectic_cadence))
                self._dialectic_depth = max(1, min(int(mem_cfg.get("dialectic_depth", self._dialectic_depth)), 3))
        except Exception:
            pass

    def _ensure_peer(self, peer_name: str, peer_type: str = "user") -> None:
        self._pg.run_sql(
            f"INSERT INTO mycortex_mem.peers (workspace, peer_name, peer_type) "
            f"VALUES ('{_esc(self._workspace)}', '{_esc(peer_name)}', '{_esc(peer_type)}') "
            f"ON CONFLICT (workspace, peer_name) DO NOTHING;",
            role="mycortex_mem_writer",
        )
        peer_id = self._resolve_peer_id(peer_name)
        if peer_id:
            self._pg.run_sql(
                f"INSERT INTO mycortex_mem.profiles (peer_id, card) "
                f"VALUES ('{peer_id}', '[]'::jsonb) ON CONFLICT (peer_id) DO NOTHING;",
                role="mycortex_mem_writer",
            )

    def _resolve_peer_id(self, peer_name: str) -> str:
        return self._pg.scalar(
            f"SELECT id::text FROM mycortex_mem.peers "
            f"WHERE workspace = '{_esc(self._workspace)}' AND peer_name = '{_esc(peer_name)}';",
        )

    def _ensure_session(self) -> None:
        self._pg.run_sql(
            f"INSERT INTO mycortex_mem.sessions (session_key) "
            f"VALUES ('{_esc(self._session_key)}') ON CONFLICT (session_key) DO NOTHING;",
            role="mycortex_mem_writer",
        )

    def system_prompt_block(self) -> str:
        if self._cron_skipped or not self._pg:
            return ""
        return (
            "# mycortex-mem Memory\n"
            "Active. Persistent memory via Postgres with 5 tools:\n"
            "- mem_profile — read/write a peer card\n"
            "- mem_search — hybrid search over past messages\n"
            "- mem_context — full session snapshot (no LLM)\n"
            "- mem_reasoning — LLM-synthesized answer to a question\n"
            "- mem_conclude — write/list/delete persistent facts\n\n"
            "For quick orientation, start with mem_profile (cheapest).\n"
            "mem_reasoning is the most expensive — use sparingly."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._cron_skipped or not self._pg:
            return ""
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
            return result

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        if self._cron_skipped or not self._pg:
            return
        if not query or len(query.strip()) < _MIN_QUERY_LEN or is_trivial_prompt(query):
            return

        def _do_prefetch():
            try:
                context = self._build_injected_context(query)
                with self._prefetch_lock:
                    self._prefetch_result = context
            except Exception as e:
                logger.debug("mycortex-mem prefetch failed: %s", e)

        self._prefetch_thread = threading.Thread(target=_do_prefetch, daemon=True, name="mem-prefetch")
        self._prefetch_thread.start()

    def _build_injected_context(self, query: str = "") -> str:
        if self._recall_mode == "tools":
            return ""
        parts = []
        card = self._get_card("user")
        if card:
            parts.append(f"## User Profile\n{card}")
        ai_card = self._get_card("ai")
        if ai_card:
            parts.append(f"## AI Identity\n{ai_card}")
        conclusions = self._search_conclusions(query or "", limit=5)
        if conclusions:
            parts.append("## Known Facts\n" + "\n".join(f"- {c}" for c in conclusions))
        if self._turn_count > 0:
            recent = self._get_recent_messages(limit=3)
            if recent:
                parts.append("## Recent Exchange\n" + "\n".join(recent))
        if not parts:
            return ""
        return "### mycortex-mem Context\n" + "\n\n".join(parts)

    def _get_card(self, peer_name: str) -> str:
        row = self._pg.scalar(
            f"SELECT card::text FROM mycortex_mem.profiles p "
            f"JOIN mycortex_mem.peers pe ON pe.id = p.peer_id "
            f"WHERE pe.workspace = '{_esc(self._workspace)}' AND pe.peer_name = '{_esc(peer_name)}';",
        )
        if not row or row == "[]":
            return ""
        try:
            facts = json.loads(row)
            if isinstance(facts, list) and facts:
                return "\n".join(f"- {f}" for f in facts[:_MAX_CARD_FACTS])
        except (json.JSONDecodeError, TypeError):
            pass
        return ""

    def _search_conclusions(self, query: str, limit: int = 5) -> list[str]:
        words = re.findall(r"\w+", query.lower())
        if not words:
            return []
        conditions = " OR ".join(f"LOWER(fact) LIKE '%{_esc(w)}%'" for w in words[:5])
        rows = self._pg.query(
            f"SELECT fact FROM mycortex_mem.conclusions c "
            f"JOIN mycortex_mem.peers p ON p.id = c.peer_id "
            f"WHERE p.workspace = '{_esc(self._workspace)}' AND NOT c.archived "
            f"AND ({conditions}) ORDER BY c.updated_at DESC LIMIT {limit};",
        )
        return [r[0] for r in rows]

    def _get_recent_messages(self, limit: int = 3) -> list[str]:
        rows = self._pg.query(
            f"SELECT m.role, substring(m.content, 1, 200) "
            f"FROM mycortex_mem.messages m "
            f"JOIN mycortex_mem.sessions s ON s.id = m.session_id "
            f"WHERE s.session_key = '{_esc(self._session_key)}' "
            f"ORDER BY m.created_at DESC LIMIT {limit};",
        )
        return [f"{r[0]}: {r[1]}" for r in reversed(rows)]

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: Optional[List[Dict[str, Any]]] = None) -> None:
        if self._cron_skipped or not self._pg:
            return
        self._turn_count += 1

        def _sync():
            try:
                self._pg.run_sql(
                    f"UPDATE mycortex_mem.sessions SET message_count = message_count + 2, "
                    f"updated_at = now() WHERE session_key = '{_esc(self._session_key)}';",
                    role="mycortex_mem_writer",
                )
                if user_content.strip():
                    self._pg.run_sql(
                        f"INSERT INTO mycortex_mem.messages (session_id, peer_id, role, content) "
                        f"SELECT s.id, '{_esc(self._user_peer_id)}', 'user', {_esc_lit(user_content[:5000])} "
                        f"FROM mycortex_mem.sessions s WHERE s.session_key = '{_esc(self._session_key)}';",
                        role="mycortex_mem_writer",
                    )
                if assistant_content.strip():
                    self._pg.run_sql(
                        f"INSERT INTO mycortex_mem.messages (session_id, peer_id, role, content) "
                        f"SELECT s.id, '{_esc(self._ai_peer_id)}', 'assistant', {_esc_lit(assistant_content[:5000])} "
                        f"FROM mycortex_mem.sessions s WHERE s.session_key = '{_esc(self._session_key)}';",
                        role="mycortex_mem_writer",
                    )
            except Exception as e:
                logger.debug("mycortex-mem sync_turn failed: %s", e)

        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)
        self._sync_thread = threading.Thread(target=_sync, daemon=True, name="mem-sync")
        self._sync_thread.start()

    def on_memory_write(self, action: str, target: str, content: str, metadata: Optional[Dict] = None) -> None:
        if self._cron_skipped or not self._pg:
            return
        if action not in {"add", "replace"} or not content:
            return
        peer_name = "ai" if target == "memory" else "user"

        def _write():
            try:
                peer_id = self._resolve_peer_id(peer_name)
                if not peer_id:
                    return
                self._pg.run_sql(
                    f"INSERT INTO mycortex_mem.conclusions (peer_id, fact, source) "
                    f"VALUES ('{peer_id}', {_esc_lit(content[:2000])}, 'agent') ON CONFLICT DO NOTHING;",
                    role="mycortex_mem_writer",
                )
            except Exception as e:
                logger.debug("mycortex-mem memory-mirror failed: %s", e)

        t = threading.Thread(target=_write, daemon=True, name="mem-mirror")
        t.start()

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if self._cron_skipped or not self._pg:
            return
        try:
            self._pg.run_sql(
                f"UPDATE mycortex_mem.sessions SET ended_at = now(), "
                f"summary = COALESCE(summary, 'Session ended after {len(messages)} messages') "
                f"WHERE session_key = '{_esc(self._session_key)}';",
                role="mycortex_mem_writer",
            )
        except Exception as e:
            logger.debug("mycortex-mem on_session_end failed: %s", e)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        # NOTE: must NOT gate on self._pg — the gateway calls add_provider()
        # (which reads this) BEFORE initialize() runs, so _pg is None at
        # registration time. Gating here emptied the executor's routing table
        # and every mem_* call failed "Unknown tool" while the system prompt
        # still advertised the schemas. The schemas are static; only cron
        # sessions and context-only recall mode suppress them.
        if self._cron_skipped:
            return []
        if self._recall_mode == "context":
            return []
        return [PROFILE_SCHEMA, SEARCH_SCHEMA, CONTEXT_SCHEMA, REASONING_SCHEMA, CONCLUDE_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        handlers = {
            "mem_profile": self._tool_profile,
            "mem_search": self._tool_search,
            "mem_context": self._tool_context,
            "mem_reasoning": self._tool_reasoning,
            "mem_conclude": self._tool_conclude,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return tool_error(f"Unknown tool: {tool_name}")
        return handler(args)

    def shutdown(self) -> None:
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=10.0)
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=5.0)

    def _tool_profile(self, args: dict) -> str:
        peer_name = args.get("peer", "user")
        card = args.get("card")
        peer_id = self._resolve_peer_id(peer_name)
        if not peer_id:
            return tool_error(f"Peer '{peer_name}' not found")
        if card is not None:
            escaped = json.dumps(list(card))
            self._pg.run_sql(
                f"UPDATE mycortex_mem.profiles SET card = '{_esc(escaped)}'::jsonb, "
                f"updated_at = now() WHERE peer_id = '{peer_id}';",
                role="mycortex_mem_writer",
            )
            return json.dumps({"result": f"Card updated for peer '{peer_name}'", "card": card})
        current = self._get_card(peer_name)
        if not current:
            current = "(no card yet — accumulates over time)"
        return json.dumps({"card": current, "peer": peer_name})

    def _tool_search(self, args: dict) -> str:
        query = args.get("query", "")
        peer_name = args.get("peer", "user")
        limit = min(int(args.get("limit", 5)), 20)
        if not query:
            return tool_error("query is required")
        words = re.findall(r"\w+", query.lower())
        if not words:
            return json.dumps({"result": "No relevant messages found."})
        peer_id = self._resolve_peer_id(peer_name)
        if not peer_id:
            return json.dumps({"result": "No messages found."})
        conditions = " OR ".join(f"LOWER(m.content) LIKE '%{_esc(w)}%'" for w in words[:5])
        rows = self._pg.query(
            f"SELECT m.role, substring(m.content, 1, 500), m.created_at "
            f"FROM mycortex_mem.messages m "
            f"WHERE m.peer_id = '{peer_id}' AND ({conditions}) "
            f"ORDER BY m.created_at DESC LIMIT {limit};",
        )
        if not rows:
            return json.dumps({"result": "No relevant messages found."})
        results = []
        for r in rows:
            results.append(f"[{r[2][:10]}] {r[0]}: {r[1]}")
        return json.dumps({"result": "\n\n".join(results)})

    def _tool_context(self, args: dict) -> str:
        peer_name = args.get("peer", "user")
        return json.dumps({"context": self._build_injected_context()})

    def _tool_reasoning(self, args: dict) -> str:
        query = args.get("query", "")
        peer_name = args.get("peer", "user")
        level = args.get("reasoning_level", "low")
        if not query:
            return tool_error("query is required")
        peer_id = self._resolve_peer_id(peer_name)
        card = self._get_card(peer_name)
        conclusions = self._search_conclusions(query, limit=10)
        evidence_parts = []
        if card:
            evidence_parts.append(f"=== Peer Card ===\n{card}")
        if conclusions:
            evidence_parts.append(f"=== Known Facts ===\n" + "\n".join(f"- {c}" for c in conclusions))
        words = re.findall(r"\w+", query.lower())
        if words and peer_id:
            conditions = " OR ".join(f"LOWER(m.content) LIKE '%{_esc(w)}%'" for w in words[:5])
            msg_rows = self._pg.query(
                f"SELECT m.role, substring(m.content, 1, 300), m.created_at "
                f"FROM mycortex_mem.messages m "
                f"WHERE m.peer_id = '{peer_id}' AND ({conditions}) "
                f"ORDER BY m.created_at DESC LIMIT 8;",
            )
            if msg_rows:
                msgs = "\n".join(f"[{r[2][:10]}] {r[0]}: {r[1]}" for r in msg_rows)
                evidence_parts.append(f"=== Relevant Messages ===\n{msgs}")
        evidence = "\n\n".join(evidence_parts) if evidence_parts else "No relevant stored information found."
        depth_instructions = {
            "minimal": "Provide a very short answer (1-2 sentences).",
            "low": "Provide a concise answer with brief evidence references.",
            "medium": "Provide a detailed answer with evidence and reasoning.",
            "high": "Thoroughly analyze the question with all available evidence.",
            "max": "Exhaustive analysis: consider contradictions, confidence levels, and multiple perspectives.",
        }
        prompt = (
            f"You are analyzing stored memory about a peer (identity: '{peer_name}').\n\n"
            f"Question: {query}\n\n"
            f"Available evidence:\n{evidence}\n\n"
            f"{depth_instructions.get(level, depth_instructions['low'])}\n\n"
            "Respond directly to the question. If evidence is insufficient, state that clearly. "
            "Do not fabricate information."
        )
        try:
            from agent.auxiliary_client import call_llm
            response = call_llm(
                task="session_search",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                timeout=_REASONING_TIMEOUT,
            )
            answer = response.choices[0].message.content.strip()
            return json.dumps({"result": answer})
        except Exception as e:
            logger.warning("mycortex-mem reasoning failed: %s", e)
            return json.dumps({"result": f"Unable to synthesize answer (reasoning unavailable: {e})", "evidence": evidence[:1000]})

    def _tool_conclude(self, args: dict) -> str:
        peer_name = args.get("peer", "user")
        conclusion = args.get("conclusion")
        delete_id = args.get("delete_id")
        do_list = args.get("list")
        query = args.get("query", "")
        peer_id = self._resolve_peer_id(peer_name)
        actions = sum(1 for x in [conclusion, delete_id, do_list] if x)
        if actions != 1:
            return tool_error("Pass exactly one of: conclusion, delete_id, or list=true")
        if conclusion:
            if not peer_id:
                return tool_error(f"Peer '{peer_name}' not found")
            self._pg.run_sql(
                f"INSERT INTO mycortex_mem.conclusions (peer_id, fact, source) "
                f"VALUES ('{peer_id}', {_esc_lit(conclusion[:2000])}, 'agent');",
                role="mycortex_mem_writer",
            )
            return json.dumps({"result": "Conclusion saved."})
        if delete_id:
            self._pg.run_sql(
                f"UPDATE mycortex_mem.conclusions SET archived = TRUE "
                f"WHERE id = '{delete_id}'::uuid;",
                role="mycortex_mem_writer",
            )
            return json.dumps({"result": "Conclusion archived."})
        if do_list:
            where = f"p.workspace = '{_esc(self._workspace)}' AND NOT c.archived"
            if query:
                qwords = re.findall(r"\w+", query.lower())
                if qwords:
                    cond = " OR ".join(f"LOWER(c.fact) LIKE '%{_esc(w)}%'" for w in qwords[:5])
                    where += f" AND ({cond})"
            rows = self._pg.query(
                f"SELECT c.id::text, c.fact, c.confidence, c.source "
                f"FROM mycortex_mem.conclusions c "
                f"JOIN mycortex_mem.peers p ON p.id = c.peer_id "
                f"WHERE {where} ORDER BY c.updated_at DESC LIMIT 20;",
            )
            if not rows:
                return json.dumps({"result": "No conclusions found."})
            items = [{"id": r[0], "fact": r[1], "confidence": r[2], "source": r[3]} for r in rows]
            return json.dumps({"conclusions": items})
        return json.dumps({"result": "No action taken."})


def _esc(val: str) -> str:
    return val.replace("'", "''")


def _esc_lit(val: str) -> str:
    return "'" + val.replace("'", "''") + "'"


def register(ctx) -> None:
    ctx.register_memory_provider(MycortexMemMemoryProvider())
