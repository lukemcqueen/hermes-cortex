#!/usr/bin/env python3
"""The reviewer's material scope: this cycle's work, not the shared working tree.

WHY (Luke, 2026-10-07, after cycle 10861): "the reviewer's material scope should be the
cycle's own commits, not the shared working tree, when peers share a checkout."

Two sessions can share ONE checkout. The material handed to the reviewer is built from
COMMITS, but the complexity measurement used to fold in EVERY staged/unstaged/untracked
path — so a peer's uncommitted files made this cycle look complex, and put the peer's
paths in the "Diff stat" the reviewer reads while their diff was nowhere in the material.
The reviewer then reports material it cannot see, and the close is refused for work this
cycle never did.

The rule now: the working tree counts only for paths whose content CHANGED SINCE THIS
CYCLE BEGAN. A file already dirty at cycle start belongs to whoever left it dirty. The
anti-dodge property is kept — a worker cannot hide its own edits by leaving them
uncommitted, because those edits change the file during the cycle.

Hermetic: a throwaway git repo in TMPDIR. No network, no governance state.

Run: python3 -m pytest tests/test_review_material_scope.py -q
"""
import importlib.util
import subprocess
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_mcp():
    spec = importlib.util.spec_from_file_location("loop_gov_mcp",
                                                  REPO / "mcp-servers" / "loop-gov-mcp.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load loop-gov-mcp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MCP = _load_mcp()


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _new_repo(tmp: Path) -> Path:
    repo = tmp / "checkout"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "base.txt").write_text("base\n")
    (repo / "peer_pre_existing.txt").write_text("tracked, clean at first\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=test@example.com", "-c", "user.name=test",
         "commit", "-q", "-m", "base")
    return repo


def _now_iso():
    # A start time AFTER the last commit -> the commit window is empty, so the test
    # measures ONLY the working-tree half (the half this change scopes).
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def test_a_peers_pre_existing_dirt_is_excluded_and_this_cycles_edits_are_counted():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))

        # A PEER leaves the checkout dirty BEFORE this cycle starts.
        (repo / "peer_pre_existing.txt").write_text("peer edit, not mine\n")
        (repo / "peer_untracked.txt").write_text("peer's loose file\n")
        snapshot = MCP._dirty_snapshot(repo)
        assert set(snapshot) == {"peer_pre_existing.txt", "peer_untracked.txt"}, snapshot

        # THIS cycle then edits its own files.
        (repo / "base.txt").write_text("my edit during the cycle\n")
        (repo / "mine_untracked.txt").write_text("my loose file\n")

        scoped = MCP._complexity(repo, _now_iso(), snapshot)
        assert "base.txt" in scoped["numstat"], scoped
        assert "peer_pre_existing.txt" not in scoped["numstat"], scoped
        assert scoped["files"] == 2, f"only this cycle's 2 files count: {scoped}"

        # The control: the SAME tree with no snapshot -> the peer's paths come back.
        wide = MCP._complexity(repo, _now_iso(), None)
        assert "peer_pre_existing.txt" in wide["numstat"], wide
        assert wide["files"] == 4, f"whole-tree behaviour counts all four: {wide}"
        print(f"  scoped files={scoped['files']} vs unscoped files={wide['files']}: the peer's "
              f"two paths are excluded only from the scoped measurement ✓")


def test_without_a_snapshot_the_whole_tree_still_counts():
    """Backwards compatibility AND the discriminating control.

    An older lock carries no snapshot; the measurement must stay exactly as strict as
    before (every dirty path counts). This is also what proves the test above is testing
    the FILTER: identical inputs, no snapshot, and the peer's file is counted again.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        (repo / "peer_pre_existing.txt").write_text("peer edit\n")
        (repo / "peer_untracked.txt").write_text("peer loose\n")

        for no_snapshot in (None, {}):
            cx = MCP._complexity(repo, _now_iso(), no_snapshot)
            assert "peer_pre_existing.txt" in cx["numstat"], \
                f"without a snapshot nothing may be narrowed (got {cx['numstat']})"
            assert cx["files"] == 2, cx
        print("  no snapshot -> whole tree counted (unchanged behaviour, fail-open) ✓")


def test_own_working_tree_paths_reports_only_what_changed_since_the_snapshot():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        (repo / "peer_pre_existing.txt").write_text("peer\n")
        snap = MCP._dirty_snapshot(repo)

        assert MCP._own_working_tree_paths(repo, snap) == set(), \
            "nothing changed since the snapshot -> nothing is this cycle's"
        (repo / "base.txt").write_text("changed during the cycle\n")
        own = MCP._own_working_tree_paths(repo, snap)
        assert own == {"base.txt"}, own

        # A file the peer TOUCHES AGAIN during the cycle cannot be told apart from ours;
        # it must be counted (fail toward review, never silently excluded).
        (repo / "peer_pre_existing.txt").write_text("peer changed again\n")
        own = MCP._own_working_tree_paths(repo, snap)
        assert own == {"base.txt", "peer_pre_existing.txt"}, own
        print("  own-paths = exactly what changed since the snapshot ✓")


def test_a_snapshot_that_cannot_be_read_never_narrows():
    """No snapshot / a cap overflow / malformed value must all keep the strict behaviour."""
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        (repo / "peer_untracked.txt").write_text("x\n")
        for bad in (None, {}, "not-a-dict", 0, []):
            assert MCP._own_working_tree_paths(repo, bad) is None, bad
        assert MCP._filter_numstat("1\t2\tsomefile\n", None) == "1\t2\tsomefile\n"
        assert MCP._filter_numstat("1\t2\tsomefile\n", set()) == ""
        print("  unreadable snapshot -> no narrowing; empty own-set -> nothing kept ✓")


def test_the_snapshot_cap_fails_open_and_says_so():
    """Over the cap the snapshot is NOT recorded — the tree stays fully in scope."""
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        (repo / "a.txt").write_text("1\n")
        (repo / "b.txt").write_text("2\n")
        assert MCP._dirty_snapshot(repo, cap=1) == {}, "over the cap must record nothing"
        assert MCP._dirty_snapshot(repo, cap=2) != {}, "at the cap the snapshot is recorded"
        print("  cap exceeded -> snapshot empty -> whole-tree scope (fail toward review) ✓")