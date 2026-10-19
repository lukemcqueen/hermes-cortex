#!/usr/bin/env python3
"""Session-scoped review window — the trailer (A1) and the own-commit scope (A2).

Reported by Titus (2026-10-19): two GOVERNED sessions in one repo, and session B's close was
refused on findings naming a file session A had committed. The cause is in the code:
`mcp-servers/loop-gov-mcp.py` builds the review window from `lock.started_at` (time-based) and
narrows it with `git log --author=<identity>` — but one host has ONE git identity, so both sessions'
commits satisfy the filter and a peer's diff enters the material, the Diff stat and the tier.

The fix has two halves that must ship together (a consumer without a producer is inert):
  A1  a `Cortex-Session: <session_id>` trailer, appended by the `prepare-commit-msg` hook from the
      LIVE governance lock (never from an env var the agent can export);
  A2  exclusion of commits whose trailer names a DIFFERENT session — fail-closed: no trailer,
      ambiguous trailer, missing own session id, or a git error ⇒ the commit STAYS in scope.

Asserted here:
  1. `_commit_session` reads a well-formed trailer; "" for absent / malformed / two values.
  2. `_excluded_session_commits` excludes ONLY a different NAMED session.
  3. Fails closed on an empty own session id and on a conflicting pair of trailers.
  4. End-to-end in a real repo, both commits by the SAME identity: B's own range holds ONLY B's
     file, while A's file is still disclosed in the provenance block (named, never reviewed).
  5. The hook: no lock ⇒ message untouched; a lock ⇒ exactly one authoritative trailer; a forged
     pre-existing trailer is replaced; exit status is 0 in every path.

Hermetic: a real `git init` under tmp_path, no store, no network, no live governance state.
"""
from __future__ import annotations

import importlib.util
import json
import logging as _logging
import os
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "loop_gov_session_scope", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
_logging.getLogger("loop-governance").setLevel(_logging.CRITICAL + 1)

HOOK = REPO / "ops" / "scripts" / "prepare-commit-msg-session"

MY_SESSION = "20261019_133021_41df6e34"
OTHER_SESSION = "20261019_090000_deadbeef"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, check=True)
    return r.stdout


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q")
    # ONE identity for both sessions — that is the whole problem.
    _git(repo, "config", "user.email", "the-agent@example.com")
    _git(repo, "config", "user.name", "the-agent")
    return repo


def _commit(repo: Path, path: str, body: str, trailer: str | None = None) -> str:
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x\n")
    _git(repo, "add", path)
    msg = body + (f"\n\nCortex-Session: {trailer}" if trailer else "")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").strip()


# ── 1. the trailer reader ──────────────────────────────────────

def test_commit_session_reads_a_well_formed_trailer(tmp_path):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "a.txt", "feat: a", trailer=MY_SESSION)
    assert mcp._commit_session(repo, sha) == MY_SESSION


def test_commit_session_is_empty_for_no_trailer(tmp_path):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "a.txt", "feat: a")
    assert mcp._commit_session(repo, sha) == ""


def test_commit_session_is_empty_when_a_body_mentions_the_word(tmp_path):
    """A prose mention is not a trailer — only a `Cortex-Session:` LINE is."""
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "a.txt", "docs: explain the Cortex-Session trailer")
    assert mcp._commit_session(repo, sha) == ""


def test_commit_session_refuses_two_conflicting_trailers(tmp_path):
    """Ambiguity is UNKNOWN, never a guess — the forged-trailer case."""
    repo = _init_repo(tmp_path)
    f = repo / "a.txt"
    f.write_text("x\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m",
         f"feat: a\n\nCortex-Session: {OTHER_SESSION}\nCortex-Session: {MY_SESSION}")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    assert mcp._commit_session(repo, sha) == ""


def test_commit_session_empty_sha_is_unknown(tmp_path):
    repo = _init_repo(tmp_path)
    assert mcp._commit_session(repo, "") == ""


# ── 2/3. the exclusion rule ────────────────────────────────────

def test_only_a_different_named_session_is_excluded(tmp_path):
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt", "chore: base")
    mine = _commit(repo, "mine.txt", "feat: mine", trailer=MY_SESSION)
    theirs = _commit(repo, "theirs.txt", "feat: theirs", trailer=OTHER_SESSION)
    untagged = _commit(repo, "legacy.txt", "feat: legacy")
    excluded = mcp._excluded_session_commits(repo, base, MY_SESSION)
    assert excluded == [theirs]
    assert mine not in excluded and untagged not in excluded


def test_exclusion_fails_closed_without_an_own_session(tmp_path):
    """No own session id ⇒ nothing is excluded (today's whole-window behaviour)."""
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt", "chore: base")
    _commit(repo, "theirs.txt", "feat: theirs", trailer=OTHER_SESSION)
    assert mcp._excluded_session_commits(repo, base, "") == []


def test_exclusion_fails_closed_on_a_conflicting_trailer(tmp_path):
    """A body carrying two trailers is UNKNOWN, so it is NOT excluded."""
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt", "chore: base")
    f = repo / "sneaky.txt"
    f.write_text("x\n")
    _git(repo, "add", "sneaky.txt")
    _git(repo, "commit", "-q", "-m",
         f"feat: sneaky\n\nCortex-Session: {OTHER_SESSION}\nCortex-Session: {MY_SESSION}")
    assert mcp._excluded_session_commits(repo, base, MY_SESSION) == []


def test_exclusion_of_a_bad_base_is_empty(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt", "feat: a", trailer=OTHER_SESSION)
    assert mcp._excluded_session_commits(repo, "", MY_SESSION) == []
    assert mcp._excluded_session_commits(repo, "HEAD", MY_SESSION) == []


# ── 4. end to end on the same git identity ─────────────────────

def test_peer_commit_leaves_my_own_range_in_a_real_repo(tmp_path):
    """A commits scripts/archive/…, B commits its own file: B's range holds only B's file."""
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt", "chore: base")
    peer = _commit(repo, "scripts/archive/data_v4_2/build_v4_2_systematic.py",
                   "chore: archive build", trailer=OTHER_SESSION)
    mine = _commit(repo, "docs/design/architecture.md", "docs: architecture", trailer=MY_SESSION)

    author = mcp._agent_author(repo)
    owned = mcp._authored_commits(repo, base, author)
    assert set(owned) == {peer, mine}, "one identity: the author filter cannot separate them"

    excluded = set(mcp._excluded_session_commits(repo, base, MY_SESSION))
    own_shas = [s for s in owned if s not in excluded]
    assert own_shas == [mine]

    numstat = mcp._git_capture(repo, "show", "--numstat", "--format=", *own_shas)
    assert "architecture.md" in numstat
    assert "build_v4_2_systematic.py" not in numstat, \
        "a peer's file must not reach my Diff stat"

    diff = mcp._git_capture(repo, "show", "-p", "--no-ext-diff", "-U3", *own_shas)
    assert "architecture.md" in diff and "build_v4_2_systematic.py" not in diff

    # …but nothing is HIDDEN: the excluded commit is disclosed by NAME (never by diff).
    prov = mcp._peer_session_block(repo, [peer])
    assert "build_v4_2_systematic.py" in prov or peer[:8] in prov
    assert "Cortex-Session" in prov


# ── 5. the hook (A1) ───────────────────────────────────────────

def _run_hook(repo: Path, tmp_path: Path, message: str, lock_session: str | None,
              source: str = "message") -> subprocess.CompletedProcess:
    deploy_home = tmp_path / "deploy"
    (deploy_home / "state").mkdir(parents=True, exist_ok=True)
    if lock_session:
        (deploy_home / "state" / ".governance-abc.json").write_text(json.dumps({
            "session_id": lock_session,
            "repo_path": str(repo),
            "repo_slug": repo.name,
            "started_at": "2026-10-19T04:30:21Z",
        }))
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(message)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "home"),
           "CORTEX_DEPLOY_HOME": str(deploy_home)}
    return subprocess.run(["bash", str(HOOK), str(msg), source], cwd=str(repo),
                          capture_output=True, text=True, env=env)


def test_hook_appends_the_trailer_from_the_live_lock(tmp_path):
    repo = _init_repo(tmp_path)
    r = _run_hook(repo, tmp_path, "feat: something", MY_SESSION)
    assert r.returncode == 0, r.stderr
    body = (tmp_path / "COMMIT_EDITMSG").read_text()
    assert body.count("Cortex-Session:") == 1
    assert f"Cortex-Session: {MY_SESSION}" in body


def test_hook_is_inert_without_a_lock(tmp_path):
    repo = _init_repo(tmp_path)
    r = _run_hook(repo, tmp_path, "feat: something", None)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "COMMIT_EDITMSG").read_text() == "feat: something"


def test_hook_replaces_a_forged_trailer(tmp_path):
    """A hand-written trailer must not survive a governed commit."""
    repo = _init_repo(tmp_path)
    forged = f"feat: something\n\nCortex-Session: {OTHER_SESSION}\n"
    r = _run_hook(repo, tmp_path, forged, MY_SESSION)
    assert r.returncode == 0, r.stderr
    body = (tmp_path / "COMMIT_EDITMSG").read_text()
    assert body.count("Cortex-Session:") == 1
    assert f"Cortex-Session: {MY_SESSION}" in body
    assert OTHER_SESSION not in body


def test_hook_is_idempotent_on_a_re_run(tmp_path):
    repo = _init_repo(tmp_path)
    _run_hook(repo, tmp_path, "feat: something", MY_SESSION)
    first = (tmp_path / "COMMIT_EDITMSG").read_text()
    _run_hook(repo, tmp_path, first, MY_SESSION)
    second = (tmp_path / "COMMIT_EDITMSG").read_text()
    assert second.count("Cortex-Session:") == 1
    assert second.strip() == first.strip()


def test_hook_never_blocks_a_commit(tmp_path):
    """Unwritable message file / unparseable lock: exit 0, always."""
    repo = _init_repo(tmp_path)
    deploy_home = tmp_path / "deploy"
    (deploy_home / "state").mkdir(parents=True, exist_ok=True)
    (deploy_home / "state" / ".governance-bad.json").write_text("{not json")
    r = subprocess.run(["bash", str(HOOK), str(tmp_path / "missing-file"), "message"],
                       cwd=str(repo), capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "home"),
                            "CORTEX_DEPLOY_HOME": str(deploy_home)})
    assert r.returncode == 0, r.stderr


def test_hook_writes_nothing_when_two_locks_share_this_repo(tmp_path):
    """TWO live locks for ONE repo ⇒ NO trailer. A pick would be a wrong attribution.

    Measured 2026-10-19 (two sessions in one repo): every commit carried the SAME id, so the close's
    session filter — which excludes a DIFFERENT id — went inert, and each session could read the
    other's commits as its own. Silence is the honest answer: the window then fails closed.
    """
    repo = _init_repo(tmp_path)
    deploy_home = tmp_path / "deploy"
    state = deploy_home / "state"
    state.mkdir(parents=True, exist_ok=True)
    for name, sid in (("a", MY_SESSION), ("b", OTHER_SESSION)):
        (state / f".governance-{name}.json").write_text(json.dumps({
            "session_id": sid, "repo_path": str(repo), "repo_slug": repo.name,
            "started_at": "2026-10-19T04:30:21Z",
        }))
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: something")
    r = subprocess.run(["bash", str(HOOK), str(msg), "message"], cwd=str(repo),
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "home"),
                            "CORTEX_DEPLOY_HOME": str(deploy_home)})
    assert r.returncode == 0, r.stderr
    assert msg.read_text() == "feat: something", "an ambiguous repo must not be stamped at all"


def test_hook_ignores_a_lock_for_a_different_repo(tmp_path):
    """A lock for another repo is not a match — the single match is still the right one."""
    repo = _init_repo(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    deploy_home = tmp_path / "deploy"
    state = deploy_home / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / ".governance-other.json").write_text(json.dumps({
        "session_id": OTHER_SESSION, "repo_path": str(other), "repo_slug": "elsewhere",
        "started_at": "2026-10-19T04:30:21Z",
    }))
    (state / ".governance-mine.json").write_text(json.dumps({
        "session_id": MY_SESSION, "repo_path": str(repo), "repo_slug": repo.name,
        "started_at": "2026-10-19T04:30:21Z",
    }))
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: something")
    r = subprocess.run(["bash", str(HOOK), str(msg), "message"], cwd=str(repo),
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "home"),
                            "CORTEX_DEPLOY_HOME": str(deploy_home)})
    assert r.returncode == 0, r.stderr
    body = msg.read_text()
    assert f"Cortex-Session: {MY_SESSION}" in body
    assert OTHER_SESSION not in body


def _write_lock(state: Path, name: str, repo: Path, sid: str, age_s: float = 0.0) -> Path:
    path = state / f".governance-{name}.json"
    path.write_text(json.dumps({"session_id": sid, "repo_path": str(repo),
                                "repo_slug": repo.name, "started_at": "2026-10-19T04:30:21Z"}))
    if age_s:
        old = time.time() - age_s
        os.utime(path, (old, old))
    return path


def _run_hook_env(repo: Path, deploy_home: Path, message: str = "feat: something"):
    msg = repo.parent / "COMMIT_EDITMSG"
    msg.write_text(message)
    r = subprocess.run(["bash", str(HOOK), str(msg), "message"], cwd=str(repo),
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(repo.parent / "home"),
                            "CORTEX_DEPLOY_HOME": str(deploy_home)})
    assert r.returncode == 0, r.stderr
    return msg.read_text()


def test_hook_attributes_to_the_freshly_active_session(tmp_path):
    """Two sessions in ONE repo: the one ACTIVE now (its lock was refreshed by a governed call)
    is stamped; the idle one's commits are not re-attributed to it.

    The lock file is rewritten on every governed call, so its mtime is that session's last governed
    activity — the only per-session signal git leaves at commit time.
    """
    repo = _init_repo(tmp_path)
    state = tmp_path / "deploy" / "state"
    state.mkdir(parents=True, exist_ok=True)
    _write_lock(state, "mine", repo, MY_SESSION)              # fresh: just touched
    _write_lock(state, "peer", repo, OTHER_SESSION, age_s=600)  # idle for 10 minutes
    body = _run_hook_env(repo, tmp_path / "deploy")
    assert body.count("Cortex-Session:") == 1
    assert f"Cortex-Session: {MY_SESSION}" in body
    assert OTHER_SESSION not in body


def test_hook_is_silent_when_two_sessions_are_both_fresh(tmp_path):
    """Both active in one repo ⇒ the hook cannot tell whose commit this is ⇒ NO trailer.

    A pick would be a mis-attribution, which is invisible and silently wrong; an absent trailer
    keeps the commit in scope for everyone (fail-closed).
    """
    repo = _init_repo(tmp_path)
    state = tmp_path / "deploy" / "state"
    state.mkdir(parents=True, exist_ok=True)
    _write_lock(state, "a", repo, MY_SESSION)
    _write_lock(state, "b", repo, OTHER_SESSION)
    assert _run_hook_env(repo, tmp_path / "deploy") == "feat: something"


def test_hook_falls_back_to_a_single_stale_candidate(tmp_path):
    """One lock, idle for a long time (a long edit before the commit): still the only claimant."""
    repo = _init_repo(tmp_path)
    state = tmp_path / "deploy" / "state"
    state.mkdir(parents=True, exist_ok=True)
    _write_lock(state, "only", repo, MY_SESSION, age_s=3600)
    body = _run_hook_env(repo, tmp_path / "deploy")
    assert f"Cortex-Session: {MY_SESSION}" in body


def test_hook_ignores_a_stale_peer_when_two_lock_the_repo(tmp_path):
    """Two claims, neither fresh ⇒ no trailer (neither session can be shown to be the author)."""
    repo = _init_repo(tmp_path)
    state = tmp_path / "deploy" / "state"
    state.mkdir(parents=True, exist_ok=True)
    _write_lock(state, "a", repo, MY_SESSION, age_s=3600)
    _write_lock(state, "b", repo, OTHER_SESSION, age_s=3600)
    assert _run_hook_env(repo, tmp_path / "deploy") == "feat: something"
