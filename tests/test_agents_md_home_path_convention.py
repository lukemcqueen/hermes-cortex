#!/usr/bin/env python3
"""AGENTS.md must not name the infra directory with a bare (un-anchored) `.hermes-cortex`.

TWO DIFFERENT DIRECTORIES SHARE THIS NAME:

  ~/.hermes-cortex/    The RUNTIME infra dir. Deployed by cortex-update.sh —
                       scripts/, state/, sessions/, memory/, hooks/, and the
                       skills.yaml the governance enforcer reads. Always written
                       with the `~/` prefix.

  ./.hermes-cortex/    A REPO-LOCAL overlay inside a CONSUMER project, created by
                       seed-project.sh. A different directory with the same name;
                       documented in docs/skills-manifest-reference.md.

Why this is pinned: AGENTS.md is the always-loaded orientation doc (it is also
copied to ~/.hermes/AGENTS.md), so a bare `.hermes-cortex` there reads as "the
Hermes agent infra directory" and sends the agent looking for the deploy home
inside the project. Operator report, 2026-10-30 (source: a seeded project
AGENTS.md on a dev host; NOT re-measured here): an agent read that file's
convention section — which listed `.hermes-cortex/sessions/`,
`.hermes-cortex/memory/` and `.hermes-cortex/skills.yaml` — and reported it as
"the Hermes agent infra directory". Verified on this host instead: all three of
those live in ~/.hermes-cortex/ (evidence:
docs/evidence/hermes-cortex-path-anchor-2026-10-30.txt; the overlay itself is
documented at docs/skills-manifest-reference.md).

Subject of this test: `AGENTS.md` at the repo root, provided by commit 43f001a6
in this range. The test needs no other file of the range to run.

The rule: every `.hermes-cortex` occurrence in AGENTS.md is home-anchored
(`~/.hermes-cortex`, `$HOME/.hermes-cortex` or `${HOME}/.hermes-cortex`).
The repo-local overlay is documented in docs/, where it can be qualified in
prose; it does not belong in AGENTS.md unqualified.

Self-contained: no fixtures, no imports beyond stdlib + pytest. Reads the
subject INSIDE each test so collection cannot fail on a missing file.
"""
import re

import pytest

ANCHORS = ("~/", "$HOME/", "${HOME}/")
TOKEN = ".hermes-cortex"


def bare_line_numbers(text):
    """Line numbers where `.hermes-cortex` appears without a home anchor."""
    hits = []
    for m in re.finditer(re.escape(TOKEN), text):
        i = m.start()
        if not any(text[max(0, i - len(a)):i] == a for a in ANCHORS):
            hits.append(text.count("\n", 0, i) + 1)
    return hits


def anchored_line_numbers(text):
    """Line numbers where `.hermes-cortex` IS home-anchored."""
    hits = []
    for m in re.finditer(re.escape(TOKEN), text):
        i = m.start()
        if any(text[max(0, i - len(a)):i] == a for a in ANCHORS):
            hits.append(text.count("\n", 0, i) + 1)
    return hits


def test_repo_agents_md_has_no_bare_hermes_cortex():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "AGENTS.md").read_text()
    bare = bare_line_numbers(text)
    assert bare == [], (
        f"AGENTS.md line(s) {bare} name `.hermes-cortex` without a home anchor. "
        f"Write `~/.hermes-cortex/...` for the runtime infra dir; a repo-local "
        f"overlay belongs in docs/ with an explicit qualifier."
    )


def test_repo_agents_md_still_names_the_runtime_dir():
    """Non-vacuous: deleting every reference must not silently pass the rule."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "AGENTS.md").read_text()
    assert anchored_line_numbers(text), (
        "AGENTS.md no longer names ~/.hermes-cortex/ at all — the agent has no "
        "pointer to the deployed infra dir. Keep the home-anchored reference."
    )


def test_deployed_agents_md_copy_when_present_is_also_clean():
    """~/.hermes/AGENTS.md is the copy agents load; drift there is the same bug."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    home_agents = Path.home() / ".hermes" / "AGENTS.md"
    if not home_agents.is_file():
        pytest.skip("no deployed ~/.hermes/AGENTS.md on this host — nothing to check")
    text = home_agents.read_text()
    bare = bare_line_numbers(text)
    assert bare == [], (
        f"deployed ~/.hermes/AGENTS.md line(s) {bare} name `.hermes-cortex` "
        f"without a home anchor: cp ~/hermes-cortex/AGENTS.md ~/.hermes/AGENTS.md"
    )
