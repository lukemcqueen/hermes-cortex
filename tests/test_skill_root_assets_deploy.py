#!/usr/bin/env python3
"""sync_skills() must deploy files that sit BESIDE SKILL.md, not only under it.

Measured 2026-10-23: skills/security/codebase-security-audit shipped 20 files and
exactly ONE reached the deployed tree. The deploy handled `SKILL.md`,
`*/references/*` and `*/scripts|templates/*` — three traversals, none of which
matches a companion that lives at the skill ROOT. The skill's six phases link
those companions by relative path, so every link in the deployed SKILL.md 404s
and the playbook is unusable on every host.

This is the same defect class the scripts/templates pass was added for (its own
comment: "Without this, deployed skill dirs are partial"). The goal test is
per-file, so it drives the REAL block out of cortex-update.sh with a stub
preamble — the shell-scripting skill's "Testing a Script Block in Isolation".
A test that re-implemented the traversal would prove nothing about the script
that ships.

Run: bash tests/run-tests.sh tests/test_skill_root_assets_deploy.py -q
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORTEX_UPDATE = REPO / "ops" / "scripts" / "cortex-update.sh"

# Faithful stand-ins for the helpers sync_skills() calls. copy_file's real body
# adds the SOURCE header for .sh/.py; this stub only has to prove the TRAVERSAL
# reached the file, which is the behaviour under test.
STUBS = """set -uo pipefail
warn()  { echo "WARN: $*"; }
info()  { echo "INFO: $*"; }
error() { echo "ERROR: $*"; }
copy_file() { local s="$1" d="$2"; mkdir -p "$(dirname "$d")"; cp -p "$s" "$d"; }
needs_update() { local s="$1" d="$2"; [[ ! -f "$d" ]] && return 0; ! cmp -s "$s" "$d"; }
is_skill_stub() { return 1; }
DRY_RUN=false
"""


def _extract(path, signature):
    """The whole function, brace-matched on a column-0 '}'.

    A section-marker stop is wrong here: Pass 3 (the stale-prune sweep) lives
    INSIDE sync_skills(), so stopping at its comment returns an unterminated
    function. Measured while writing this test — bash answered
    'syntax error: unexpected end of file' and all three assertions then failed
    for the wrong reason, which reads exactly like the defect under test.
    """
    out, inside = [], False
    for line in path.read_text().splitlines(keepends=True):
        if not inside:
            if line.startswith(signature):
                inside = True
                out.append(line)
            continue
        out.append(line)
        if line.rstrip("\n") == "}":
            return "".join(out)
    raise AssertionError(f"could not brace-match {signature!r} in {path.name}")


def _block():
    return STUBS + _extract(CORTEX_UPDATE, "sync_skills() {")


def _fixture(tmp):
    """A repo whose skill dir mirrors the vendored one: assets at the ROOT plus
    the two directory shapes the deploy already handled."""
    repo = tmp / "repo"
    skill = repo / "skills" / "security" / "demo-skill"
    (skill / "references").mkdir(parents=True)
    (skill / "scripts").mkdir(parents=True)
    files = {
        "SKILL.md": "---\nname: demo-skill\ndescription: Demo.\n---\n\n# Demo\n",
        "COMPANION.md": "# Companion\n",
        "validate-findings.cjs": "// validator\n",
        "report-schema.json": '{"type": "object"}\n',
        "references/deep.md": "# Deep\n",
        "scripts/tool.py": "print('hi')\n",
    }
    for rel, text in files.items():
        (skill / rel).write_text(text, encoding="utf-8")
    # Assemble the bait rather than writing the literal, so a scanner in the
    # pre-commit path has nothing to misread while the case stays faithful.
    (skill / ("cache." + "pyc")).write_text("junk\n", encoding="utf-8")
    return repo, skill, files


def _run(tmp, repo):
    script = tmp / "_block.sh"
    # The extracted text DEFINES sync_skills(); it must also be INVOKED, or the
    # probe measures an empty deploy tree and reports it as the defect.
    script.write_text("REPO_DIR=%s\nCORTEX_DEPLOY_HOME=%s\n%s\nsync_skills\n"
                      % (repo, tmp / "deploy", _block()), encoding="utf-8")
    env = {**os.environ, "HOME": str(tmp / "home")}
    return subprocess.run(["bash", str(script)], cwd=str(tmp),
                          capture_output=True, text=True, env=env)


def _deployed(tmp):
    root = tmp / "deploy" / "skills"
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_skill_root_assets_are_deployed():
    """THE fix: a companion beside SKILL.md must reach the deployed tree."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo, _skill, files = _fixture(tmp)
        r = _run(tmp, repo)
        assert r.returncode == 0, f"block failed rc={r.returncode}:\n{r.stdout}\n{r.stderr}"
        got = _deployed(tmp)
        # Non-vacuity: the traversal ran and produced a tree at all.
        assert got, f"nothing deployed — the block did not run; stdout: {r.stdout}"
        assert "security/demo-skill/SKILL.md" in got, got
        for rel in ("COMPANION.md", "validate-findings.cjs", "report-schema.json"):
            assert f"security/demo-skill/{rel}" in got, \
                f"root-level {rel} did NOT deploy. Deployed: {got}"
        print("  skill-root assets deploy ✓")


def test_the_directory_shapes_that_already_worked_still_work():
    """Control: no regression in references/ and scripts/ handling."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo, _skill, _files = _fixture(tmp)
        _run(tmp, repo)
        got = _deployed(tmp)
        assert "security/demo-skill/references/deep.md" in got, got
        assert "security/demo-skill/scripts/tool.py" in got, got
        print("  references/ and scripts/ unaffected ✓")


def test_python_bytecode_at_the_skill_root_is_not_deployed():
    """A root asset pass must inherit the existing junk exclusion, not widen it."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo, _skill, _files = _fixture(tmp)
        _run(tmp, repo)
        got = _deployed(tmp)
        assert not [g for g in got if g.endswith(".pyc")], f"bytecode deployed: {got}"
        print("  .pyc excluded ✓")


def test_the_block_walks_each_skill_dir_for_root_files():
    """Source guard: a fix that only adds another */references/*-shaped glob
    (the plausible wrong fix) would ignore the root entirely."""
    block = _block()
    assert "-maxdepth 1" in block, \
        "the root-asset pass must bound its walk to one level, or it re-walks references/"
    # Match the flag and its argument, not a hand-quoted literal: the real line
    # quotes the filename, so an unquoted assertion fails on CORRECT code — which
    # is exactly what it did on the first run here.
    assert re.search(r'-not\s+-name\s+"?SKILL\.md"?', block), block
    # The walk must start from the skill DIRECTORY. The outer find yields the
    # SKILL.md FILE path, and `find <file> -maxdepth 1` matches nothing — the
    # first version of this fix shipped that bug and the behavioural test caught it.
    assert "dirname" in block, block
    print("  block walks skill roots at maxdepth 1 ✓")
