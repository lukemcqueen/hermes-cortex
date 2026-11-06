#!/usr/bin/env python3
"""AGENTS.md must not name the infra directory with a bare (un-anchored) `.steadfaste-fleet`.

TWO DIFFERENT DIRECTORIES SHARE THIS NAME:

  ~/.steadfaste-fleet/    The RUNTIME infra dir. Deployed by fleet-update.sh —
                       scripts/, state/, sessions/, memory/, hooks/, and the
                       skills.yaml the governance enforcer reads. Always written
                       with the `~/` prefix.

  ./.steadfaste-fleet/    A REPO-LOCAL overlay inside a CONSUMER project, created by
                       seed-project.sh. A different directory with the same name;
                       documented in docs/skills-manifest-reference.md.

Why this is pinned: AGENTS.md is the always-loaded orientation doc (it is also
copied to ~/.hermes/AGENTS.md), so a bare `.steadfaste-fleet` there reads as "the
Hermes agent infra directory" and sends the agent looking for the deploy home
inside the project. Operator report, 2026-10-30 (source: a seeded project
AGENTS.md on a dev host; NOT re-measured here): an agent read that file's
convention section — which listed `.steadfaste-fleet/sessions/`,
`.steadfaste-fleet/memory/` and `.steadfaste-fleet/skills.yaml` — and reported it as
"the Hermes agent infra directory". Verified on this host instead: all three of
those live in ~/.steadfaste-fleet/ (evidence:
docs/evidence/steadfaste-fleet-path-anchor-2026-10-30.txt; the overlay itself is
documented at docs/skills-manifest-reference.md).

Subject of this test: `AGENTS.md` at the repo root, provided by commit 43f001a6
in this range. The test needs no other file of the range to run.

The rule: every `.steadfaste-fleet` occurrence in AGENTS.md is home-anchored
(`~/.steadfaste-fleet`, `$HOME/.steadfaste-fleet` or `${HOME}/.steadfaste-fleet`).
The repo-local overlay is documented in docs/, where it can be qualified in
prose; it does not belong in AGENTS.md unqualified.

Self-contained: no fixtures, no imports beyond stdlib + pytest. Reads the
subject INSIDE each test so collection cannot fail on a missing file.
"""
import re

import pytest

ANCHORS = ("~/", "$HOME/", "${HOME}/")
TOKEN = ".steadfaste-fleet"


def bare_line_numbers(text):
    """Line numbers where `.steadfaste-fleet` appears without a home anchor."""
    hits = []
    for m in re.finditer(re.escape(TOKEN), text):
        i = m.start()
        if not any(text[max(0, i - len(a)):i] == a for a in ANCHORS):
            hits.append(text.count("\n", 0, i) + 1)
    return hits


def anchored_line_numbers(text):
    """Line numbers where `.steadfaste-fleet` IS home-anchored."""
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
        f"AGENTS.md line(s) {bare} name `.steadfaste-fleet` without a home anchor. "
        f"Write `~/.steadfaste-fleet/...` for the runtime infra dir; a repo-local "
        f"overlay belongs in docs/ with an explicit qualifier."
    )


def test_repo_agents_md_still_names_the_runtime_dir():
    """Non-vacuous: deleting every reference must not silently pass the rule."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "AGENTS.md").read_text()
    assert anchored_line_numbers(text), (
        "AGENTS.md no longer names ~/.steadfaste-fleet/ at all — the agent has no "
        "pointer to the deployed infra dir. Keep the home-anchored reference."
    )


def test_fleet_template_still_clearly_addresses_the_runtime_dir():
    """Non-vacuous for the template: the seeded project AGENTS.md must address
    the runtime infra dir with a home anchor, and keep naming the split."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    template = repo_root / "docs" / "templates" / "AGENTS.seed.md"
    if not template.is_file():
        pytest.skip("no AGENTS.seed.md template — nothing to check")
    text = template.read_text()
    # The template must mention the fleet source with a home anchor
    assert "~/.steadfaste-fleet" in text or "~/steadfaste-fleet" in text or "$HOME/.steadfaste-fleet" in text or "${HOME}/.steadfaste-fleet" in text, (
        "AGENTS.seed.md no longer names the fleet source — the per-repo seed has "
        "no pointer to the shared template/skills source."
    )
    # The template must not carry the old global-copy instruction
    assert "~/.hermes/AGENTS.md" not in text, (
        "AGENTS.seed.md still instructs a ~/.hermes/AGENTS.md copy — AGENTS is "
        "per-repo since the ~/.hermes sync was removed (Luke 2026-11-04)."
    )
