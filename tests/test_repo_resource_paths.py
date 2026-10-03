#!/usr/bin/env python3
"""One resolver for repo-vs-deployed paths — and the MCP servers must use it.

The bug this guards: the deployed path of a repo file CANNOT be derived from the
repo path. cortex-update.sh's register() map is per-file — 192 of 289 entries
follow no rule (ops/scripts/manage/task-db.py → scripts/task-db.py, but
ops/scripts/manage/agent-no-verify-audit.py → scripts/manage/…). So every
component that guessed looked in a directory that exists in only ONE layout, and
a guess that resolved in the repo failed AFTER a deploy, on a host, far from the
edit. loop-gov-mcp's judgment lookup was one such guess: its first candidate,
<deploy>/tools/ops/scripts/judgment.py, exists in NEITHER layout.

The fix: cortex-update.sh writes its own map out as `deploy-manifest.tsv`, and
cortex_lib.paths.resolve_repo_resource() READS it. These tests hold that line.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PATHS_PY = REPO / "ops/scripts/cortex_lib/paths.py"
UPDATE_SH = REPO / "ops/scripts/cortex-update.sh"
MCP_DIR = REPO / "mcp-servers"

# The repo-relative resources the MCP servers resolve. Add a row here when a
# server starts loading a new sibling — that is the point of the list.
RESOLVED_BY_SERVERS = {
    "mcp-servers/cortex-context-mcp.py": "ops/services/mycortex-mem/context_tools.py",
    "mcp-servers/task-mcp.py": "ops/scripts/manage/task-db.py",
    "mcp-servers/loop-gov-mcp.py": "ops/scripts/judgment.py",
}


def _load_paths():
    spec = importlib.util.spec_from_file_location("cortex_lib_paths_under_test", PATHS_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── the resolver itself ─────────────────────────────────────────────

def test_resolver_resolves_every_resource_the_mcp_servers_ask_for():
    paths = _load_paths()
    for server, rel in RESOLVED_BY_SERVERS.items():
        found = paths.resolve_repo_resource(rel)
        assert found is not None, (
            f"{server} asks for {rel} and the resolver cannot find it. "
            f"Tried: {[str(p) for p in paths.repo_resource_candidates(rel)]}")
        assert found.is_file()


def test_resolver_failure_reports_where_it_looked():
    """A resource that cannot be found is a component that will not work, so the
    failure must NAME the candidates — not just say 'not found'."""
    paths = _load_paths()
    missing = "ops/scripts/definitely-not-a-real-file.py"
    assert paths.resolve_repo_resource(missing) is None
    candidates = paths.repo_resource_candidates(missing)
    assert candidates, "a miss must still report the paths it tried"
    assert any("deploy-manifest" in str(c) for c in candidates), (
        "the report must show the manifest lookup, or a reader cannot tell "
        "whether the file is missing or the manifest is")


def test_resolver_never_guesses_a_deployed_path():
    """The deployed answer comes from the manifest ONLY — a stripped-`ops/` guess
    is what silently resolved in the repo and failed after a deploy."""
    paths = _load_paths()
    src = PATHS_PY.read_text()
    assert "deploy-manifest" in src, "the resolver must consult the manifest"
    assert "strip" not in src.lower() or "never guessed" in src, \
        "no path-stripping heuristic may come back"
    # Scope this to the RESOLVER's body. A whole-file grep flags its own
    # explanation: `~/.hermes-cortex/scripts` legitimately appears in
    # ensure_scripts_path's docstring, and this assertion caught that prose rather
    # than the code (the probe was wrong, not the resolver).
    body = src.split("def resolve_repo_resource", 1)[1].split(
        "def repo_resource_candidates", 1)[0]
    assert "hermes-cortex/scripts" not in body, \
        "no hard-coded deployed candidate in the resolver — that is the hand-rolled list this replaced"


# ── the manifest is the single source of truth ──────────────────────

def test_cortex_update_emits_the_manifest():
    src = UPDATE_SH.read_text()
    assert "_write_deploy_manifest()" in src, "cortex-update.sh must define the emitter"
    assert "_write_deploy_manifest \"${entries[@]}\"" in src, \
        "the emitter must be called with the real register() map"
    assert "deploy-manifest.tsv" in src, "the manifest name must be the documented one"
    # It is generated from the map, never maintained by hand.
    assert "do not edit" in src.lower()


def test_manifest_covers_every_resource_the_servers_ask_for():
    """On a DEPLOYED host the manifest must have an entry for each resource.

    Reads the deployed manifest directly, so the guard actually RUNS where it
    matters (the repo has no manifest and does not need one — its paths are
    already correct — so a walk-up lookup alone would always skip here).
    """
    paths = _load_paths()
    manifest = paths.deploy_manifest()
    if not manifest:
        deployed = Path.home() / ".hermes-cortex" / "deploy-manifest.tsv"
        if not deployed.is_file():
            pytest.skip("no deploy-manifest.tsv on this host")
        manifest = paths.read_manifest(deployed)
    assert manifest, "the deployed manifest parsed empty"
    for server, rel in RESOLVED_BY_SERVERS.items():
        assert rel in manifest, (
            f"{rel} (used by {server}) has no deploy-manifest entry — the server "
            "will not find it on a deployed host")


def test_cortex_update_syntax_is_valid():
    r = subprocess.run(["bash", "-n", str(UPDATE_SH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── the servers use the resolver, not their own list ────────────────

@pytest.mark.parametrize("server", sorted(RESOLVED_BY_SERVERS))
def test_mcp_server_uses_the_shared_resolver(server):
    src = (REPO / server).read_text()
    assert "resolve_repo_resource" in src, (
        f"{server} must resolve its sibling through cortex_lib.paths — a "
        "hand-rolled candidate list is the bug this replaces")
    assert "repo_resource_candidates" in src, (
        f"{server} must report where it looked when the resource is missing")


def test_no_mcp_server_hand_rolls_a_candidate_list_for_a_repo_resource():
    """The old shape: a local tuple/list of guessed paths. It looks reasonable and
    is wrong, because the deployed path is not derivable."""
    offenders = []
    for path in sorted(MCP_DIR.glob("*.py")):
        src = path.read_text()
        if "resolve_repo_resource" in src:
            continue
        for marker in ("_CANDIDATES = [", "cand in (Path(__file__)",
                       "parents[1] / \"ops\""):
            if marker in src:
                offenders.append(f"{path.name}: {marker}")
    assert not offenders, (
        "these servers still guess a repo resource's location:\n  "
        + "\n  ".join(offenders))


# ── one bootstrap idiom, byte-identical ─────────────────────────────

BOOTSTRAP_START = ("# ── cortex_lib bootstrap — IDENTICAL in every MCP server; "
                   "do not vary. ─────")
BOOTSTRAP_END = "except ImportError:\n    pass\n"


def _bootstrap_block(text: str) -> str:
    body = text.split(BOOTSTRAP_START, 1)[1]
    return BOOTSTRAP_START + body.split(BOOTSTRAP_END, 1)[0] + BOOTSTRAP_END


def test_every_mcp_server_carries_the_identical_bootstrap():
    """A per-server bootstrap is how the servers drifted apart the first time: each
    guessed a different relative depth. The block is one idiom — if it must change,
    it changes in every server at once, and this test is what forces that."""
    blocks = {}
    for path in sorted(MCP_DIR.glob("*.py")):
        text = path.read_text()
        if BOOTSTRAP_START in text:
            blocks[path.name] = _bootstrap_block(text)
    assert blocks, "no MCP server carries the canonical cortex_lib bootstrap"
    reference_name, reference = next(iter(blocks.items()))
    drifted = [n for n, b in blocks.items() if b != reference]
    assert not drifted, (
        f"these servers have a DIFFERENT cortex_lib bootstrap than "
        f"{reference_name}: {drifted}. One idiom, or they drift again.")
    assert len(blocks) >= 3, (
        f"only {len(blocks)} server(s) carry the bootstrap; the servers that "
        "resolve a repo resource must all use it")


def test_servers_declare_their_resource_as_a_named_constant():
    """`_TOOLS_REL` / `_TASK_DB_REL` / `_JUDGMENT_REL` — the repo-relative path is
    named once and passed to the resolver, so the error message and the lookup
    cannot disagree about what was wanted."""
    for server in sorted(RESOLVED_BY_SERVERS):
        src = (REPO / server).read_text()
        assert "_REL = \"" in src, (
            f"{server} must name its repo-relative resource in a `_…_REL` "
            "constant and hand that to the resolver")


# ── a registered file must actually be IN git ───────────────────────

def test_every_registered_file_is_tracked_by_git():
    """A registered file that git IGNORES deploys from the working tree and nowhere else.

    `cortex-update.sh` reads the WORKING TREE, so a gitignored source file still
    deploys on the machine where it was written — while every other host, and any
    fresh clone, never receives it. `.gitignore` carries broad secret patterns
    (`*token*`, `*secret*`, `*cred*`), so a source file whose NAME trips one of them
    goes untracked silently, and nothing else notices.

    That is not hypothetical: it happened to the live-token guard. It deployed here,
    both units referenced it, the tests read it from disk — and it was absent from
    the commit, so the unit's ExecStartPre pointed at a file no other host has.
    """
    rows = re.findall(
        r'^(?:register|register_orch)\s+"([^"]+)"\s+"\$\{CORTEX_DEPLOY_HOME\}/[^"]+"',
        UPDATE_SH.read_text(), re.M)
    assert rows, "no register() rows parsed — fix the parser, not the assertion"

    untracked = []
    for src_rel in rows:
        if not (REPO / src_rel).exists():
            continue                      # absent from the repo: a different failure
        r = subprocess.run(["git", "ls-files", "--error-unmatch", src_rel],
                           cwd=REPO, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            untracked.append(src_rel)
    assert not untracked, (
        "these registered files are NOT tracked by git, so they deploy from the "
        "working tree only and never reach another host:\n  "
        + "\n  ".join(untracked))
