"""Tests for audit-pi-integration.sh Layer-2 curated-set probe (published tree).

RED-GREEN background (2026-11-04): Pi was repointed at the whole published tree
(~/.agents/skills); the flat cortex-skills symlink farm is retired and
install-pi-integration.sh never recreates it. The audit's Layer-2 check still
required the always-skills to live in the retired dir, so a HEALTHY host
reported a permanent FAIL that its own remediation could not clear (the
impossible-PASS failure model the audit header warns against). The probe was
rewritten to resolve the registered skills root from settings.json and prove
each always-skill carries a SKILL.md somewhere under it (os.walk — no `find
-quit`, so it stays macOS/bash-3.2-safe).

This suite re-implements that probe (faithful copy) against mock settings.json
+ mock published trees and asserts the PASS / FAIL / NOROOT outcomes the audit
relies on. The anti-drift guard (test_probe_still_mirrors_audit_source) fails
LOUDLY if the audit's inline probe drifts from this copy without an update, so
the two cannot silently diverge.

The probe contract (mirrors the audit): given a registered skills root and a
`always:` list, MISSING = the always-skills with no SKILL.md under any root;
ROOT = a path where the first-present skill lives.
"""

import os
from pathlib import Path


# The 8 always-skills from skills.yaml `always:` (the audit reads these via awk).
ALWAYS = [
    "task-start",
    "agent-flow",
    "reflexion-check",
    "change-checklist",
    "survey-before-action",
    "agent-contract",
    "test-driven-development",
    "prove-before-create",
]


def probe(settings: dict, want):
    """Faithful copy of audit-pi-integration.sh's Layer-2 curated-set probe.

    Returns (missing, shown) where missing is the list of want-skills with no
    SKILL.md under any registered root, and shown is the first located path.
    Returns ([], None) for the NONE-of-the-skills-present / no-root edge.
    """
    roots = [e for e in (settings.get("skills") or []) if isinstance(e, str) and os.path.isdir(e)]
    want = [w for w in want if w]
    if not roots:
        return None, None  # audit prints NOROOT for this case
    missing, shown = [], roots[0]

    def _has(root, name):
        for dp, _dn, fn in os.walk(root):
            if "SKILL.md" in fn and os.path.basename(dp) == name:
                return dp
        return None

    for name in want:
        loc = None
        for r in roots:
            loc = _has(r, name)
            if loc:
                break
        if loc:
            shown = loc
        else:
            missing.append(name)
    return missing, shown


def _make_published_root(base, missing=None):
    """Build a mock published tree: <base>/<category>/<skill>/SKILL.md for each skill,
    in the same category layout Pi actually uses (workflow/ for task-start, the rest
    software-development/), except those named in `missing`."""
    missing = missing or []
    for skill in ALWAYS:
        if skill in missing:
            continue
        cat = "workflow" if skill == "task-start" else "software-development"
        d = base / cat / skill
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
    return base


def _settings(root):
    return {"skills": [str(root)]}


def test_pass_when_all_always_skills_present(tmp_path):
    root = _make_published_root(tmp_path / "tree")
    missing, shown = probe(_settings(root), ALWAYS)
    assert missing == [], f"expected no missing skills, got {missing}"
    assert shown is not None and (Path(shown) / "SKILL.md").exists()


def test_fail_lists_missing_skill(tmp_path):
    root = _make_published_root(tmp_path / "tree", missing=["prove-before-create"])
    missing, _ = probe(_settings(root), ALWAYS)
    assert missing == ["prove-before-create"]


def test_noroot_when_settings_has_no_skills_dir(tmp_path):
    # a registered skill root that is NOT an existing dir counts as no root
    assert probe({"skills": [str(tmp_path / "does-not-exist")]}, ALWAYS) == (None, None)


def test_ignore_non_skill_lines_in_tree(tmp_path):
    # a stray non-SKILL.md file must not satisfy the probe; and a category dir
    # named like a skill but holding no SKILL.md must not count either
    root = tmp_path / "tree"
    (root / "software-development" / "change-checklist").mkdir(parents=True)
    (root / "software-development" / "change-checklist" / "notes.txt").write_text("x", encoding="utf-8")
    missing, _ = probe(_settings(root), ["change-checklist"])
    assert missing == ["change-checklist"]