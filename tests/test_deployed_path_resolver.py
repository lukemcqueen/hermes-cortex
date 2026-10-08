#!/usr/bin/env python3
"""The deployed-path resolver: an evidence probe must ASK, never mirror the repo layout.

Regression guard for a real false finding. A probe assumed
``<deploy home>/mcp-servers/loop-gov-mcp.py`` — the REPO layout — and, wrapped in
``2>/dev/null || echo "<conclusion>"``, printed "0 (deployed copy predates this commit)" into
a committed evidence file. The real destination is
``<deploy home>/tools/loop-governance/loop-gov-mcp.py``, and the deployed copy already
carried the change, so the sentence was false in both halves.

Controls here, because a guard that cannot fail is indistinguishable from one that is not
looking:
  * the resolver returns the DESTINATION and never the repo copy (the discriminating control)
  * an unregistered source is COULD NOT RESOLVE (exit 2) and prints no path
  * a registered source with nothing at the destination is COULD NOT VERIFY (exit 3)
  * a missing or unreadable map is loud (exit 2), never an empty answer
  * on a deployed host, the real map resolves the loop-gov server (skipped without a map)

Run: python3 -m pytest tests/test_deployed_path_resolver.py -q
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "ops" / "scripts" / "manage" / "deployed-path.py"


def _run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True)


def _fixture(tmp, rows, create_destinations=True):
    """Write a manifest into `tmp`, creating destination files unless told not to."""
    manifest = Path(tmp) / "deploy-manifest.tsv"
    lines = []
    for src, dst in rows.items():
        lines.append(f"{src}\t{dst}")
        if create_destinations:
            dest = Path(dst)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("deployed content\n")
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def test_it_returns_the_destination_never_the_repo_copy():
    """THE control for the bug: both a repo copy and a deployed copy exist, and the repo
    copy is the tempting wrong answer."""
    with tempfile.TemporaryDirectory() as td:
        src = "mcp-servers/loop-gov-mcp.py"
        assert (REPO / src).is_file(), "premise: a repo copy exists to be mistaken for it"
        dest = Path(td) / "tools" / "loop-governance" / "loop-gov-mcp.py"
        manifest = _fixture(td, {src: str(dest)})

        result = _run(src, "--manifest", str(manifest))
        assert result.returncode == 0, result
        assert result.stdout.strip() == str(dest), result.stdout
        assert str(REPO / src) != result.stdout.strip(), \
            "the repo copy must never be returned as the deployed destination"
        print(f"  destination returned: {result.stdout.strip()} (not the repo copy) ✓")


def test_an_unregistered_source_is_could_not_resolve_and_prints_no_path():
    with tempfile.TemporaryDirectory() as td:
        manifest = _fixture(td, {"some/other.py": str(Path(td) / "x" / "other.py")})
        result = _run("mcp-servers/never-registered.py", "--manifest", str(manifest))
        assert result.returncode == 2, result
        assert "COULD NOT RESOLVE" in result.stdout, result.stdout
        assert not result.stdout.strip().splitlines()[-1].startswith("/"), \
            "a failure must not print a path that could be mistaken for the answer"
        print("  unregistered source -> COULD NOT RESOLVE, no path ✓")


def test_a_registered_source_with_nothing_there_is_could_not_verify():
    with tempfile.TemporaryDirectory() as td:
        src = "mcp-servers/loop-gov-mcp.py"
        dest = Path(td) / "tools" / "loop-governance" / "loop-gov-mcp.py"   # never created
        manifest = _fixture(td, {src: str(dest)}, create_destinations=False)
        result = _run(src, "--manifest", str(manifest))
        assert result.returncode == 3, result
        assert "COULD NOT VERIFY" in result.stdout, result.stdout
        print("  registered but absent -> COULD NOT VERIFY (exit 3) ✓")


def test_a_missing_map_is_loud_never_an_empty_answer():
    with tempfile.TemporaryDirectory() as td:
        result = _run("mcp-servers/loop-gov-mcp.py",
                      "--manifest", str(Path(td) / "nope.tsv"))
        assert result.returncode == 2, result
        assert "COULD NOT RESOLVE" in result.stdout, result.stdout
        assert "Nothing was checked" in result.stdout, result.stdout
        print("  missing map -> COULD NOT RESOLVE, and says nothing was checked ✓")


def test_the_host_map_resolves_the_loop_gov_server():
    """On a deployed host: the real map, and the deployed file really is there."""
    manifest = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex"))
    manifest = manifest / "deploy-manifest.tsv"
    if not manifest.is_file():
        print("  (no host deploy-manifest.tsv — skipped)")
        return
    result = _run("mcp-servers/loop-gov-mcp.py")
    assert result.returncode == 0, result
    resolved = Path(result.stdout.strip())
    assert resolved.is_file(), resolved
    assert "loop-governance" in resolved.parts, \
        f"the loop-gov server deploys under tools/loop-governance, got {resolved}"
    print(f"  host map resolves it to {resolved} ✓")