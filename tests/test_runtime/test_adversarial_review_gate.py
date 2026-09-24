"""Event-driven adversarial review gate — complexity + verdict unit tests.

Covers the measured (never self-reported) complexity signal and the
fail-closed verdict extraction that gate end_change. Reviewer independence
and hard-gate semantics are tested here; the model call itself is exercised
live, not in unit tests.
"""
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_gate", MCP)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# ── _parse_numstat ──────────────────────────────────────────────────────────

def test_numstat_counts_added_and_removed_separately():
    text = "10\t2\tfoo.py\n0\t0\tbar.md\n-\t-\tbinary.bin\n"
    files, added, removed = mod._parse_numstat(text)
    assert files == {"foo.py", "bar.md", "binary.bin"}
    assert added == 10
    assert removed == 2


def test_numstat_ignores_binary_and_malformed():
    text = "-\t-\tl.img\n5\t1\tx.py\nbroken\n"
    files, added, removed = mod._parse_numstat(text)
    assert "l.img" in files  # binary still counted as a touched file
    assert added == 5
    assert removed == 1


# ── _is_noise (exact-name only) ────────────────────────────────────────────

def test_noise_is_exact_name_match():
    assert mod._is_noise("Cargo.lock")
    assert mod._is_noise("sub/dir/Cargo.lock")
    assert not mod._is_noise("src/main.rs")
    assert not mod._is_noise("Cargo.lock.rs")  # suffix trick must NOT match


# ── _extract_verdict (fail-closed) ─────────────────────────────────────────

def test_extract_clean_verdict():
    verdict, findings = mod._extract_verdict(
        '{"verdict": "CLEAN", "findings": [], "summary": "probed all"}')
    assert verdict == "CLEAN"
    assert json.loads(findings) == []


def test_extract_findings_verdict():
    text = 'some prose {"verdict": "FINDINGS", "findings": [{"finding_id": "ADV-1"}]} trailing'
    verdict, findings = mod._extract_verdict(text)
    assert verdict == "FINDINGS"
    assert json.loads(findings)[0]["finding_id"] == "ADV-1"


def test_extract_unparseable_is_findings_not_clean():
    # Fail-closed: a reply that is not valid JSON can never be trusted as CLEAN.
    verdict, findings = mod._extract_verdict("i refuse to answer in json")
    assert verdict == "FINDINGS"
    assert json.loads(findings) == []


# ── _complexity (measured, diff-based) ─────────────────────────────────────

@pytest.fixture()
def git_repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    # Isolate from the global hermes-cortex hooksPath — test commits must not
    # run the real pre-commit hook (which writes state artifacts into the repo).
    subprocess.run(["git", "-C", str(r), "config", "core.hooksPath", "/dev/null"], check=True)
    subprocess.run(["git", "-C", str(r), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(r), "config", "user.name", "test"], check=True)
    (r / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "init"], check=True)
    return r


def _commit(r, files: dict, msg="wip"):
    for name, content in files.items():
        p = r / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", msg], check=True)


def test_small_change_is_simple(git_repo):
    _commit(git_repo, {"src/a.py": "x = 1\n"})
    cx = mod._complexity(git_repo, "1970-01-01T00:00:00Z")
    assert cx["is_complex"] is False


def test_large_change_is_complex(git_repo):
    _commit(git_repo, {"src/a.py": ("x = 1\n" * 100)})
    cx = mod._complexity(git_repo, "1970-01-01T00:00:00Z")
    assert cx["is_complex"] is True
    assert cx["lines"] >= mod.COMPLEXITY_LINE_THRESHOLD


def test_net_zero_rewrite_is_complex(git_repo):
    # Replace 100 lines with 100 different lines: added+removed counted
    # separately, so a rewrite is still complex (not a net-zero dodge).
    _commit(git_repo, {"src/a.py": ("old\n" * 60)})
    _commit(git_repo, {"src/a.py": ("new\n" * 60)})
    cx = mod._complexity(git_repo, "1970-01-01T00:00:00Z")
    assert cx["is_complex"] is True


def test_always_review_path_is_complex_regardless_of_size(git_repo):
    _commit(git_repo, {"plugins/governance-enforcer/__init__.py": "x=1\n"})
    cx = mod._complexity(git_repo, "1970-01-01T00:00:00Z")
    assert cx["is_complex"] is True
    assert cx["always_review"] is True


def test_lockfile_only_is_simple(git_repo):
    # A pure lockfile bump is discounted — not a complexity signal.
    _commit(git_repo, {"Cargo.lock": ("dep\n" * 200)})
    cx = mod._complexity(git_repo, "1970-01-01T00:00:00Z")
    assert cx["is_complex"] is False


def test_uncommitted_change_counts(git_repo):
    # Dirty working tree (unstaged) still counts toward complexity.
    (git_repo / "src" / "big.py").parent.mkdir(parents=True, exist_ok=True)
    (git_repo / "src" / "big.py").write_text("z = 1\n" * 80)
    cx = mod._complexity(git_repo, "1970-01-01T00:00:00Z")
    assert cx["is_complex"] is True


# ── gate: simple skip, no reviewer call ─────────────────────────────────────

def test_gate_skips_simple_change_without_reviewer(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "config", "core.hooksPath", "/dev/null"], check=True)
    subprocess.run(["git", "-C", str(r), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(r), "config", "user.name", "test"], check=True)
    (r / "README.md").write_text("hi\n")
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "init"], check=True)
    (r / "x.md").write_text("tiny\n")

    # If the reviewer were (incorrectly) called, this would blow up.
    def _boom(*a, **k):
        raise AssertionError("reviewer must not be called for a simple change")
    monkeypatch.setattr(mod, "_call_reviewer", _boom)

    lock = {"repo_slug": r.name, "task_id": "t", "description": "d",
            "started_at": "1970-01-01T00:00:00Z"}
    cycle = {"id": 1, "outcome_note": "note"}
    monkeypatch.setattr(mod, "HOME", tmp_path)
    result = mod._adversarial_review_gate(lock, cycle)
    assert result is None  # proceeds


def test_gate_fails_closed_when_repo_missing(monkeypatch):
    monkeypatch.setattr(mod, "HOME", Path(tempfile.mkdtemp()))
    lock = {"repo_slug": "no-such-repo", "started_at": "1970-01-01T00:00:00Z"}
    result = mod._adversarial_review_gate(lock, {"id": 1})
    assert result is not None
    text = result.content[0].text
    assert "Cannot close" in text
