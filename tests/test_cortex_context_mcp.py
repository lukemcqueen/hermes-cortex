#!/usr/bin/env python3
"""cortex-context-mcp + store — memory and session over ONE store (S2c).

Covers the three decisions the design makes (docs/design/cortex-memory-session-mcp.md):
  1. session identity is explicit and derivable, never "latest";
  2. checkpoint = structured facts, not a transcript;
  3. memory and session are two views of ONE store (so `mem_context` can carry
     the session checkpoint, and `session_close` can promote decisions to memory).

Hermetic: an injected fake psql seam — no live database. The real MCP wire
protocol is exercised separately at the bottom.

Run: python3 -m pytest tests/test_cortex_context_mcp.py -q
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Obviously-fake identifiers (lettered, never digit runs) so the PII guard and
# a reader both see them as placeholders.
FAKE_PEER_ID = "aaaaaaa1-bbbb-cccc-dddd-eeeeeeeeeee1"
FAKE_SESSION_ID = "aaaaaaa2-bbbb-cccc-dddd-eeeeeeeeeee2"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def store_mod():
    return _load(REPO / "ops" / "services" / "mycortex-mem" / "store.py", "cortex_store_t")


class FakePg:
    """Records SQL instead of running it. `scalar`/`row` return canned values."""

    def __init__(self, scalars=None, rows=None):
        self.sql = []
        self._scalars = list(scalars or [])
        self._rows = list(rows or [])

    def run_sql(self, sql, role="w", timeout=10):
        self.sql.append(("write", sql))
        return ""

    def query(self, sql, role="r", timeout=10):
        self.sql.append(("read", sql))
        return []

    def scalar(self, sql, role="r", default="", timeout=10):
        self.sql.append(("scalar", sql))
        return self._scalars.pop(0) if self._scalars else default

    def row(self, sql, role="r"):
        self.sql.append(("row", sql))
        return self._rows.pop(0) if self._rows else None

    def available(self, timeout=3):
        return True


# ── Session identity: explicit + derivable, never "latest" ────

def test_session_key_is_derived_from_harness_repo_branch(store_mod):
    assert store_mod.SessionStore.session_key("pi", "hermes-cortex", "main") == \
        "pi:hermes-cortex:main"


def test_session_key_skips_empty_parts(store_mod):
    assert store_mod.SessionStore.session_key("pi", "", "main") == "pi:main"


def test_session_key_is_bounded(store_mod):
    """A pathological path must not overflow the column."""
    key = store_mod.SessionStore.session_key("pi", "x" * 500, "main")
    assert len(key) <= 200


# ── Memory: the store owns identity resolution (one path) ─────

def test_peer_id_upserts_then_resolves(store_mod):
    pg = FakePg(scalars=[FAKE_PEER_ID])
    mem = store_mod.MemoryStore(pg)
    assert mem.peer_id("user") == FAKE_PEER_ID
    writes = " ".join(s for kind, s in pg.sql if kind == "write")
    assert "INSERT INTO mycortex_mem.peers" in writes and "ON CONFLICT" in writes


def test_card_write_casts_to_jsonb(store_mod):
    pg = FakePg(scalars=[FAKE_PEER_ID])
    store_mod.MemoryStore(pg).set_card(["prefers terse answers"], "user")
    writes = " ".join(s for kind, s in pg.sql if kind == "write")
    assert "::jsonb" in writes, "card must be written as jsonb, not text"


def test_search_messages_uses_full_text_not_ilike(store_mod):
    """One ranking path: the same FTS the session search uses."""
    pg = FakePg()
    store_mod.MemoryStore(pg).search_messages("gateway", limit=3)
    sql = " ".join(s for kind, s in pg.sql if kind == "read")
    assert "plainto_tsquery" in sql, "must use Postgres FTS, not a LIKE scan"


def test_conclusion_delete_archives_not_deletes(store_mod):
    """History is never destroyed — facts are archived."""
    pg = FakePg(scalars=[FAKE_PEER_ID])
    store_mod.MemoryStore(pg).delete_conclusion("c-1")
    writes = " ".join(s for kind, s in pg.sql if kind == "write")
    assert "archived = TRUE" in writes
    assert "DELETE FROM" not in writes.upper()


# ── Session: checkpoint is facts, restore is deterministic ────

def test_checkpoint_is_append_only(store_mod):
    pg = FakePg(scalars=[FAKE_SESSION_ID])
    s = store_mod.SessionStore(pg)
    s.checkpoint("pi", "repo", "main", done=["a"], pending=["b"], blockers=["c"],
                 decisions=["d"], notes="n")
    writes = [s_ for kind, s_ in pg.sql if kind == "write"]
    joined = " ".join(writes)
    assert "INSERT INTO mycortex_mem.checkpoints" in joined
    assert not any("DELETE" in w.upper() for w in writes), "append-only, never destructive"


def test_checkpoint_roundtrip_parses_structured_facts(store_mod):
    row = ["cp-1", '["did x"]', '["todo y"]', '["blocked z"]', '["chose w"]',
           "note", "stamp", "pi:repo:main"]
    assert store_mod.SessionStore._row_to_checkpoint(row) == {
        "checkpoint_id": "cp-1", "done": ["did x"], "pending": ["todo y"],
        "blockers": ["blocked z"], "decisions": ["chose w"], "notes": "note",
        "at": "stamp", "session_key": "pi:repo:main",
    }


def test_restore_of_missing_checkpoint_is_none_not_an_error(store_mod):
    assert store_mod.SessionStore._row_to_checkpoint(None) is None, \
        "an unknown session is empty, never an exception"


def test_malformed_json_degrades_to_empty_list(store_mod):
    """A corrupt row must not take the whole restore down."""
    row = ["cp-1", "{not json", "[]", "[]", "[]", "n", "t", "k"]
    snap = store_mod.SessionStore._row_to_checkpoint(row)
    assert snap["done"] == [] and snap["pending"] == []


# ── The seam: one store, two views ───────────────────────────

def test_store_exposes_both_views_over_one_connection(store_mod):
    pg = FakePg()
    s = store_mod.Store(pg)
    assert s.memory is not None and s.sessions is not None
    assert s.memory.pg is pg and s.sessions.pg is pg, "one connection, not two"


def test_close_can_promote_decisions_into_memory(store_mod):
    """The mix/match seam: checkpoint decisions become durable facts."""
    row = ["cp-1", "[]", "[]", "[]", '["use postgres"]', "n", "t", "pi:repo:main"]
    pg = FakePg(scalars=[FAKE_PEER_ID], rows=[row, FAKE_SESSION_ID])
    store_mod.SessionStore(pg).close("pi", "repo", "main", promote_decisions=True)
    writes = " ".join(s_ for kind, s_ in pg.sql if kind == "write")
    assert "INSERT INTO mycortex_mem.conclusions" in writes
    assert "use postgres" in writes


def test_close_does_not_promote_unless_asked(store_mod):
    row = ["cp-1", "[]", "[]", "[]", '["keep local"]', "n", "t", "pi:repo:main"]
    pg = FakePg(scalars=[FAKE_PEER_ID], rows=[row, FAKE_SESSION_ID])
    store_mod.SessionStore(pg).close("pi", "repo", "main", promote_decisions=False)
    writes = " ".join(s_ for kind, s_ in pg.sql if kind == "write")
    assert "INSERT INTO mycortex_mem.conclusions" not in writes


def test_session_search_covers_state_and_history(store_mod):
    """One query surface: structured state AND messages, so the two cannot drift."""
    pg = FakePg()
    hits = store_mod.SessionStore(pg).search("gateway envelope")
    assert {h["kind"] for h in hits} <= {"checkpoint", "message"}
    reads = " ".join(s for kind, s in pg.sql if kind == "read")
    assert "checkpoints" in reads and "messages" in reads


# ── The MCP server: tool surface + fail-open ─────────────────

def _load_server():
    return _load(REPO / "mcp-servers" / "cortex-context-mcp.py", "cortex_context_mcp_t")


def _load_tools():
    """The tool surface lives in the SHARED module now, not in the server: the
    MCP server and the CLI are both thin access layers over it."""
    return _load(REPO / "ops" / "services" / "mycortex-mem" / "context_tools.py",
                 "context_tools_mcp_t")


def test_server_declares_both_families():
    pytest.importorskip("mcp")
    names = {t["name"] for t in _load_tools().TOOLS}
    mem = {n for n in names if n.startswith("mem_")}
    ses = {n for n in names if n.startswith("session_")}
    assert mem == {"mem_profile", "mem_search", "mem_context", "mem_conclude"}, mem
    # The session seam is part of the shared surface now (memory/session seam):
    # checkpoint/restore/list/note/close plus the loaded-skill and tool-event
    # records the governance gates read. Pinned exactly — a tool that appears
    # here without a handler is a routing hole, and one that vanishes silently
    # breaks whichever gate asked for it.
    assert ses == {"session_checkpoint", "session_restore", "session_list",
                   "session_search", "session_note", "session_close",
                   "session_loaded_skill", "session_tool_event"}, ses


def test_every_declared_tool_has_a_handler():
    pytest.importorskip("mcp")
    tools = _load_tools()
    for t in tools.TOOLS:
        assert t["name"] in tools.HANDLERS, f"{t['name']} has no handler"


def test_fail_open_message_is_not_an_exception():
    pytest.importorskip("mcp")
    msg = _load_tools().UNAVAILABLE
    assert "unavailable" in msg and "not an error" in msg


def test_identity_precedence_args_beat_env(monkeypatch):
    pytest.importorskip("mcp")
    tools = _load_tools()
    monkeypatch.setenv("CORTEX_SESSION_HARNESS", "envharness")
    assert tools.resolve_identity({"harness": "argharness"})[0] == "argharness"
    assert tools.resolve_identity({})[0] == "envharness"


def test_explicit_session_key_env_wins_outright(monkeypatch):
    pytest.importorskip("mcp")
    tools = _load_tools()
    monkeypatch.setenv("CORTEX_SESSION_KEY", "pi:repo:main")
    assert tools.resolve_identity({}) == ("pi:repo:main", "", "")


def test_session_key_includes_all_three_axes(monkeypatch):
    pytest.importorskip("mcp")
    srv = _load_server()
    monkeypatch.delenv("CORTEX_SESSION_KEY", raising=False)
    monkeypatch.setenv("CORTEX_SESSION_HARNESS", "pi")
    monkeypatch.setenv("CORTEX_SESSION_REPO", "hermes-cortex")
    monkeypatch.setenv("CORTEX_SESSION_BRANCH", "main")
    assert _load_tools().session_key_from({}) == "pi:hermes-cortex:main"


# ── Real wire protocol: the server actually speaks MCP ───────

def test_server_completes_a_real_mcp_handshake():
    """Start the server over stdio and list its tools over the real protocol —
    proves the SDK wiring, not just the module's shape. The protocol version is
    read from the SDK rather than hardcoded, so it cannot go stale.

    Read INCREMENTALLY rather than writing everything and closing stdin: a stdio
    server exits on stdin EOF, so a one-shot write races the flush of the final
    response. That race is a property of the test, not the server — a real client
    holds stdin open — so the test must not encode it.
    """
    mcp_types = pytest.importorskip("mcp.types")
    event = importlib.import_module("threading").Event()
    script = REPO / "mcp-servers" / "cortex-context-mcp.py"
    py = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"
    py = str(py) if py.is_file() else sys.executable
    version = getattr(mcp_types, "LATEST_PROTOCOL_VERSION", None) or \
        getattr(mcp_types, "DEFAULT_NEGOTIATED_VERSION", "")

    proc = subprocess.Popen([py, str(script)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out_lines: list[str] = []

    def _drain() -> None:
        for line in proc.stdout:              # type: ignore[union-attr]
            out_lines.append(line)
            try:
                if json.loads(line).get("id") == 2:
                    event.set()               # tools/list answered — done
            except Exception:
                pass

    reader = importlib.import_module("threading").Thread(target=_drain, daemon=True)
    reader.start()

    def send(obj: dict) -> None:
        proc.stdin.write(json.dumps(obj) + "\n")   # type: ignore[union-attr]
        proc.stdin.flush()                          # type: ignore[union-attr]

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": version, "capabilities": {},
                     "clientInfo": {"name": "probe", "version": "1"}}})
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    got = event.wait(timeout=30)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    out = "".join(out_lines)
    assert got, f"tools/list never answered: {out[-400:]}"
    assert "session_checkpoint" in out, f"session family missing: {out[-400:]}"
    assert "mem_profile" in out, f"memory family missing: {out[-400:]}"
