#!/usr/bin/env python3
"""Review attribution — a peer's commits must never be charged to this worker.

Luke (2026-10-02): "The adversarial reviewer is structurally misattributing esther's
upstream work to my cycle" (Titus). His lock window (lock start → HEAD) held commits
that a pull brought in — MY edits to the always-review paths (mcp-servers/loop-gov-mcp.py,
ops/scripts/cortex-update.sh). The reviewer read that diff, charged it to him, and
rejected his (real) evidence as fabrication. Retries re-rolled the same verdict.

Two structural causes, both fixed here and both asserted against a REAL git repo:

  A. The material builder labelled foreign commits ONLY when this session's identity
     resolved. On a host where it did not resolve, the whole window went in
     UNLABELLED — so foreign work looked like the worker's own.
  B. The reviewer's constitution made "verified with no output attached" a
     FABRICATION (critical/high), while the reviewer can never see a worker's
     terminal. Fabrication now requires a CONTRADICTION in the material, and the
     resolution for missing proof is to COMMIT it as a test — checkable later, unlike
     a pasted transcript.

The labels come from git, not from the worker's note, so they cannot be forged by
prose — and nothing is hidden: every commit stays in the material either way.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_attr", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

OWN = "esther@example.com"
PEER = "titus@example.com"
_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


def _git(repo: Path, *args: str, author: str | None = None) -> str:
    env = dict(os.environ)
    if author:
        env.update({"GIT_AUTHOR_NAME": author.split("@")[0], "GIT_AUTHOR_EMAIL": author,
                    "GIT_COMMITTER_NAME": author.split("@")[0], "GIT_COMMITTER_EMAIL": author})
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, env=env).stdout


def _repo(tmp: Path) -> tuple[Path, str]:
    """Real repo: c1 setup (OWN) → c2 foreign peer → c3 OWN. Returns (repo, base=c1)."""
    repo = tmp / "r"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", OWN)
    _git(repo, "config", "user.name", "esther")
    (repo / "f.txt").write_text("setup\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup", author=OWN)
    base = _git(repo, "rev-parse", "HEAD").strip()
    # the peer's commit — pulled into the window, touches an always-review path
    (repo / "mcp-servers").mkdir()
    (repo / "mcp-servers" / "loop-gov-mcp.py").write_text("# peer enforcement edit\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "peer enforcement change", author=PEER)
    # this session's own commit
    (repo / "own.txt").write_text("worker's change\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "worker change", author=OWN)
    return repo, base


def test_review_attribution() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo, base = _repo(Path(td))

        print("A. identity UNRESOLVED — every commit is labelled (was: unlabelled window)")
        block = mcp._provenance_block(repo, base, "")
        _check("block is produced", bool(block.strip()))
        _check("names the peer's author", PEER in block, block[:200])
        _check("names this session's author too", OWN in block)
        _check("states the peer commit is NOT part of this cycle",
               "NOT part of this cycle" in block, block[:300])
        _check("tells the reviewer how to attribute",
               "ONLY where git shows this session authored" in block)

        print("A2. identity RESOLVED — own commits excluded, peer's disclosed")
        block2 = mcp._provenance_block(repo, base, OWN)
        _check("discloses the peer commit", PEER in block2)
        _check("does NOT list this session's own commit",
               "worker change" not in block2, block2[:200])
        _check("says these are NOT authored by this session",
               "NOT authored by this session" in block2)

        print("A3. no foreign commits → no spurious provenance noise")
        repo2, base2 = _repo(Path(td) / "second")
        # window with only OWN commits: base = the peer commit
        peer_base = _git(repo2, "rev-parse", "HEAD~1").strip()
        _check("empty block when all commits are this session's",
               mcp._provenance_block(repo2, peer_base, OWN).strip() == "")

    print("B. the constitution no longer treats invisible terminals as fabrication")
    tmpl = (REPO / "docs" / "templates" / "adversarial-reviewer-prompt.md").read_text()
    _check("fabrication requires a contradiction in the material",
           "Fabrication requires positive" in tmpl and "CONTRADICTS" in tmpl)
    _check("states the terminal cannot be seen by construction",
           "you cannot see a terminal BY" in tmpl)
    _check("resolution is committed proof, not a pasted transcript",
           "COMMITTED as a runnable test" in tmpl)
    _check("carries the misattribution rule",
           "**Misattribution**" in tmpl and "ONLY where git shows this session authored" in tmpl)

    assert not _F, f"{len(_F)} attribution check(s) failed: {', '.join(_F)}"


if __name__ == "__main__":
    test_review_attribution()
    print("\n✅ review attribution checks passed")
    sys.exit(0)
