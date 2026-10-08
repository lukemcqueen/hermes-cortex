#!/usr/bin/env python3
"""The reviewer's material must be SELF-CONSISTENT: every path named in the
"Diff stat" must have its diff present in the material's diff body.

WHY (cycle 10877, finding ADV-10877-1, severity critical, technique fabrication):

    "Worker's note states: 'HEAD is unchanged at 8d4452d8 and this session
     authored zero commits'. The diff stat header claims 11 files changed with
     578 lines of changes... A diff stat of non-zero changes with an unchanged
     HEAD is a contradiction — either commits exist or the diff stat is
     fabricated."

The reviewer was right. The material's diff BODY is built from commits
(`git log -p --author=...`), but its "Diff stat" line was built from a DIFFERENT
basis — the complexity measurement, which deliberately ALSO counts the cycle's
own staged/unstaged/untracked edits. Two consequences, both reproduced below:

  1. No snapshot (an older lock, or one over the 300-path cap) => EVERY dirty
     path lands in the Diff stat, a peer's included, while their diff is absent.
     This is what produced files=11, lines=578 against an empty diff.
  2. Even WITH a correct snapshot, the cycle's OWN uncommitted edits land in the
     Diff stat while the diff body stays empty — same contradiction, and the
     snapshot fix (801926ec) does not touch it.

So the material needs the same rule the measurement already applies — this
cycle's own paths, not the shared working tree — plus the invariant that makes
it safe: a path may never be NAMED in the material without its diff being shown.

The measurement itself is deliberately unchanged: `_complexity` must keep
counting the cycle's own uncommitted work, or a worker could dodge the gate by
leaving risky edits uncommitted. Only the MATERIAL is scoped.

Hermetic: throwaway git repos in TMPDIR, deterministic commit dates (no sleeps,
no clock races). No network, no governance state.

Run: python3 -m pytest tests/test_review_material_consistency.py -q
"""
import importlib.util
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Deterministic clock: base commit -> cycle starts -> the cycle's own commit.
BASE_DATE = "2026-01-01T00:00:00+00:00"
STARTED_AT = "2026-01-02T00:00:00Z"
MINE_DATE = "2026-01-03T00:00:00+00:00"


def _load_mcp():
    spec = importlib.util.spec_from_file_location(
        "loop_gov_mcp", REPO / "mcp-servers" / "loop-gov-mcp.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load loop-gov-mcp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MCP = _load_mcp()
AUTHOR = "test@example.com"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def _commit(repo, msg, date):
    env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    return subprocess.run(
        ["git", "-C", str(repo), "-c", f"user.email={AUTHOR}",
         "-c", "user.name=test", "commit", "-q", "-m", msg],
        capture_output=True, text=True, env={**_env(), **env})


def _env():
    import os
    return dict(os.environ)


def _new_repo(tmp: Path) -> Path:
    repo = tmp / "checkout"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", AUTHOR)
    _git(repo, "config", "user.name", "test")
    (repo / "base.txt").write_text("base\n")
    (repo / "peer.txt").write_text("tracked\n")
    _git(repo, "add", "-A")
    _commit(repo, "base", BASE_DATE)
    return repo


def _scope(repo, cx, authored=None):
    """Call the helper under test with the same inputs the gate uses."""
    base = MCP._git_capture(
        repo, "rev-list", "-1", "--before=" + STARTED_AT, "HEAD").strip() or "HEAD"
    author = MCP._agent_author(repo)
    if authored is None:
        authored = bool(MCP._authored_commits(repo, base, author))
    return MCP._material_scope(repo, base, author, authored, cx), base


def _named_paths(numstat: str) -> set:
    out = set()
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].strip():
            out.add(parts[2].strip())
    return out


def _body_paths(repo, base, author, authored) -> set:
    """Paths the material's diff BODY actually shows (what the reviewer can see)."""
    if authored:
        text = MCP._git_capture(repo, "log", "--numstat", "--format=",
                                "--author=" + author, base + "..HEAD")
    else:
        text = MCP._git_capture(repo, "diff", "--numstat", base + "..HEAD")
    return _named_paths(text)


def test_a_peers_pre_existing_dirt_is_never_named_in_the_material():
    """No snapshot + no commit: the peer's 11-file case. Stat must name NOTHING.

    This is cycle 10877 exactly — files=11, lines=578 against an empty diff.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        # A peer leaves the shared checkout dirty BEFORE this cycle opens.
        (repo / "peer.txt").write_text("peer edit, not mine\n")
        (repo / "peer_loose.txt").write_text("peer's loose file\n")

        cx = MCP._complexity(repo, STARTED_AT, None)      # old lock: no snapshot
        assert cx["files"] == 2, f"the MEASUREMENT must still count both: {cx}"

        scope, base = _scope(repo, cx)
        named = _named_paths(scope["numstat"])
        assert named == set(), \
            f"no path may be named without its diff in the material, got {named}"
        assert scope["files"] == 0 and scope["lines"] == 0, scope
        # ...and the exclusion is DISCLOSED, never silent.
        assert set(scope["excluded"]) == {"peer.txt", "peer_loose.txt"}, scope

        body = _body_paths(repo, base, MCP._agent_author(repo), False)
        assert named <= body, "invariant: Diff stat must be a subset of the diff body"
        print(f"  peer dirt: measurement counts {cx['files']}, material names 0, "
              f"discloses {scope['excluded']} ✓")


def test_this_cycles_own_uncommitted_edit_is_never_named_without_its_diff():
    """WITH a correct snapshot: the cycle's own uncommitted edit. Same rule.

    The snapshot fix (801926ec) removes the peer's files but NOT this case —
    `_complexity` counts the cycle's own edit, so the Diff stat still named a
    path whose diff the material never showed.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        (repo / "peer.txt").write_text("peer edit\n")     # peer dirt first
        snapshot = MCP._dirty_snapshot(repo)              # ...recorded at start

        (repo / "base.txt").write_text("my uncommitted change\n")  # THIS cycle

        cx = MCP._complexity(repo, STARTED_AT, snapshot)
        assert cx["files"] == 1, f"anti-dodge: the cycle's own edit must count: {cx}"
        assert "peer.txt" not in cx["numstat"], "the peer's file is scoped out"

        scope, base = _scope(repo, cx)
        named = _named_paths(scope["numstat"])
        assert named == set(), \
            f"the diff body is empty, so nothing may be named; got {named}"
        assert scope["excluded"] == ["base.txt"], scope
        assert named <= _body_paths(repo, base, MCP._agent_author(repo), False)
        print(f"  own uncommitted edit: measurement counts {cx['files']}, "
              f"material names 0, discloses {scope['excluded']} ✓")


def test_committed_work_is_still_named_with_its_counts():
    """The discriminating positive control: a real commit MUST be reported.

    Without this, a 'fix' that simply blanks the Diff stat would pass the two
    tests above and destroy the material's usefulness.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        (repo / "base.txt").write_text("base\none\ntwo\n")     # purely additive: +2
        _git(repo, "add", "-A")
        _commit(repo, "my change", MINE_DATE)

        cx = MCP._complexity(repo, STARTED_AT, None)
        assert cx["files"] == 1 and cx["lines"] == 2, cx

        scope, base = _scope(repo, cx)
        assert _named_paths(scope["numstat"]) == {"base.txt"}, scope
        assert scope["files"] == 1 and scope["lines"] == 2, scope
        assert scope["excluded"] == [], scope
        body = _body_paths(repo, base, MCP._agent_author(repo), True)
        assert _named_paths(scope["numstat"]) <= body, "stat ⊆ body"
        print("  committed work: named with files=1 lines=2, nothing excluded ✓")


def test_the_stat_never_exceeds_the_body_when_both_halves_are_present():
    """Both at once: a committed change AND leftover uncommitted edits.

    The committed half is named; the uncommitted half is disclosed, not named.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        (repo / "base.txt").write_text("committed change\n")
        _git(repo, "add", "-A")
        _commit(repo, "my change", MINE_DATE)
        (repo / "leftover.txt").write_text("still uncommitted\n")

        cx = MCP._complexity(repo, STARTED_AT, None)
        scope, base = _scope(repo, cx)
        named = _named_paths(scope["numstat"])
        body = _body_paths(repo, base, MCP._agent_author(repo), True)
        assert named == {"base.txt"}, scope
        assert named <= body, "invariant: stat ⊆ body"
        assert scope["excluded"] == ["leftover.txt"], scope
        print("  mixed: committed 'base.txt' named, 'leftover.txt' disclosed ✓")


def test_a_committed_rename_is_not_falsely_disclosed():
    """A rename row's path field is `old => new`; the path at HEAD is the RHS.

    Found by the A4 boundary pass (B6): comparing the raw field made a committed
    rename that was ALSO dirty look out-of-scope, so the material disclosed a path
    whose diff it was showing — a false disclosure, the safe direction but still wrong.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(Path(td))
        _git(repo, "mv", "peer.txt", "renamed.txt")
        _commit(repo, "rename peer.txt", MINE_DATE)
        base = MCP._git_capture(
            repo, "rev-list", "-1", "--before=" + STARTED_AT, "HEAD").strip()
        author = MCP._agent_author(repo)

        scope = MCP._material_scope(repo, base, author, True,
                                    {"worktree_files": ["renamed.txt"]})
        assert scope["excluded"] == [], \
            f"a committed rename must not be disclosed as out-of-scope: {scope}"
        assert "renamed.txt" in MCP._range_path_set(scope["numstat"]), scope
        print("  committed rename: resolved to its HEAD-side name, not disclosed ✓")


def test_rename_path_set_handles_every_git_rename_form():
    assert MCP._range_path_set("1\t1\told.txt => new.txt\n") >= {"old.txt => new.txt",
                                                                 "new.txt"}
    assert MCP._range_path_set("1\t1\tdir/{a.txt => b.txt}\n") >= {"dir/b.txt"}
    assert MCP._range_path_set("1\t1\tdir/{a.txt => b.txt}/tail\n") >= \
        {"dir/b.txt/tail"}, MCP._range_path_set("1\t1\tdir/{a.txt => b.txt}/tail\n")
    assert MCP._range_path_set("") == set()
    assert MCP._range_path_set("not-a-numstat-line\n") == set()
    print("  rename forms: bare, braced, braced-with-suffix, empty, malformed ✓")


if __name__ == "__main__":
    for fn in (test_a_peers_pre_existing_dirt_is_never_named_in_the_material,
               test_this_cycles_own_uncommitted_edit_is_never_named_without_its_diff,
               test_committed_work_is_still_named_with_its_counts,
               test_the_stat_never_exceeds_the_body_when_both_halves_are_present,
               test_a_committed_rename_is_not_falsely_disclosed,
               test_rename_path_set_handles_every_git_rename_form):
        fn()
    print("ALL PASS — the reviewer's material is self-consistent")
