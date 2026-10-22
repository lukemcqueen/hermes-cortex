"""Tests for the skills-loadability doctor check (cortex_doctor.checks).

The check exists because a SKILL.md that fails the Agent-Skills rules is DROPPED
from every coding agent's skill index without an error anyone reads (measured
2026-10-22: 30 deprecated redirect stubs had no `description`, so the redirect
they exist to deliver reached no agent at all).

Every rule is pinned in BOTH directions — the input it must report, and the input
it must stay silent on — because a check verified only in the reporting direction
cannot show that it is quiet on a healthy tree, and one verified only in the
silent direction may have been deleted. The success path and the no-parser path
get their own cases: the line that reports a HEALTHY result is the least-tested
branch of a checker.

Run: bash tests/run-tests.sh tests/test_skills_loadable_check.py -q
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402

GOOD = """---
name: good-skill
description: A skill every loader accepts.
version: 1.0.0
---

# Good
"""


def _skill(root: Path, rel: str, text: str) -> Path:
    p = root / "skills" / rel / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _run(monkeypatch, tmp_path, files):
    """Build a fabricated repo + a redirected HOME, run the check, return (Results, repo)."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        _skill(repo, rel, text)
    monkeypatch.setattr(checks, "CORTEX_REPO", repo)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))   # no ~/.agents/skills here
    res = Results()
    checks.check_skills_loadable(res)
    return res, repo


def _defects(path, mod=yaml):
    """Call the check's validator with a chosen yaml module (None = text mode)."""
    return checks._skill_defects(path, mod)


def _statuses(res):
    return {c["status"] for c in res.checks}


# ── the individual rules, each with a passing counterpart ─────────────────────

def test_accepts_a_well_formed_skill(tmp_path):
    p = _skill(tmp_path, "devops/good", GOOD)
    assert _defects(p) == []


def test_reports_missing_description(tmp_path):
    p = _skill(tmp_path, "devops/stub",
               "---\nname: stub\nversion: 1.0.0\ndeprecated: true\n---\n\n# Stub\n")
    assert _defects(p) == ["description is required"]


def test_blank_description_counts_as_missing(tmp_path):
    p = _skill(tmp_path, "devops/blank", '---\nname: blank\ndescription: "   "\n---\n\n# B\n')
    assert "description is required" in _defects(p)


def test_reports_unquoted_colon_description(tmp_path):
    """The task-persistence shape: ': ' inside an unquoted scalar is invalid YAML."""
    p = _skill(tmp_path, "devops/colon",
               "---\nname: colon\nversion: 1.0.0\n"
               "description: Tasks via task-db.py. v2: story/slices, paused.\n---\n\n# C\n")
    defects = _defects(p)
    assert defects and defects[0].startswith("frontmatter does not parse:")


def test_quoted_colon_description_is_accepted(tmp_path):
    p = _skill(tmp_path, "devops/colon-ok",
               '---\nname: colon-ok\nversion: 1.0.0\n'
               'description: "Tasks via task-db.py. v2: story/slices, paused."\n---\n\n# C\n')
    assert _defects(p) == []


def test_reports_duplicate_mapping_key(tmp_path):
    """PyYAML silently keeps the LAST duplicate key; the loader REJECTS the file.

    The check must therefore see what the loader sees, not what PyYAML tolerates —
    asserted here so the node walk cannot be replaced by a plain safe_load().
    """
    text = ("---\nname: dup\nversion: 1.0.0\ntags:\n  - a\n  - b\nversion: 2.0.0\n"
            "description: Dup keys.\n---\n\n# D\n")
    p = _skill(tmp_path, "devops/dup", text)
    assert yaml.safe_load(text[3:text.find("\n---", 3)]) is not None, "PyYAML must accept it"
    assert any(d.startswith("duplicate mapping key(s):") for d in _defects(p))


def test_reports_invalid_name_charset(tmp_path):
    p = _skill(tmp_path, "productivity/here-now",
               "---\nname: here.now\ndescription: Publish sites.\n---\n\n# H\n")
    assert any("invalid characters" in d for d in _defects(p))


def test_reports_missing_frontmatter(tmp_path):
    p = _skill(tmp_path, "brand-intelligence",
               "# Brand Intelligence\n\nNo frontmatter at all.\n")
    assert _defects(p) == ["no frontmatter (file does not start with ---)"]


def test_reports_missing_name(tmp_path):
    p = _skill(tmp_path, "software-development/lite-pr",
               "---\ntitle: lite-pr\ndescription: A PRD template.\n---\n\n# L\n")
    assert "name is required" in _defects(p)


# ── the check itself, in both directions ──────────────────────────────────────

def test_check_fails_on_a_broken_repo_tree(monkeypatch, tmp_path):
    res, _ = _run(monkeypatch, tmp_path, {
        "devops/stub": "---\nname: stub\nversion: 1.0.0\n---\n\n# S\n",
        "devops/good": GOOD,
    })
    assert "FAIL" in _statuses(res)
    assert any("description is required" in c["detail"] for c in res.checks)
    assert not any(c["status"] == "PASS" for c in res.checks), \
        "a tree with a refused skill must not also report a PASS line"


def test_check_passes_on_a_clean_repo_tree(monkeypatch, tmp_path):
    """The SUCCESS path: the line that reports a healthy result must be reachable."""
    res, _ = _run(monkeypatch, tmp_path, {"devops/good": GOOD})
    assert _statuses(res) == {"PASS"}
    assert "all 1 repo skills pass" in res.checks[0]["detail"]


def test_recursion_stops_at_a_directory_holding_skill_md(monkeypatch, tmp_path):
    """A nested SKILL.md below a skill root is INVISIBLE to a loader.

    brand-intelligence/ is the live example: its own SKILL.md ends the walk, so
    three nested skills/ entries are never loaded and must not be counted here.
    """
    res, repo = _run(monkeypatch, tmp_path, {
        "brand-intelligence": "# no frontmatter\n",
        "brand-intelligence/skills/brand-brief": "# also none\n",
    })
    assert len(checks._loader_skill_files(repo / "skills")) == 1


def test_no_yaml_parser_degrades_to_text_and_never_fakes_a_pass(monkeypatch, tmp_path):
    """Without PyYAML the check degrades to a TEXT scan — and must NOT report PASS.

    Measured 2026-10-22 on esther: the doctor runs under whatever `python3` is on
    PATH, and that is the Hermes runtime venv, which has no yaml. The first cut of
    this check then reported `unchecked=383` AND a PASS line saying all 383 skills
    passed — a green tick over files it never read. That is the regression this
    test pins.
    """
    monkeypatch.setitem(sys.modules, "yaml", None)     # makes `import yaml` raise
    with pytest.raises(ImportError):
        __import__("yaml")

    good = _skill(tmp_path, "devops/good", GOOD)
    stub = _skill(tmp_path, "devops/stub", "---\nname: stub\nversion: 1.0.0\n---\n\n# S\n")
    assert _defects(good, None) == [], "text mode must accept a well-formed file"
    assert _defects(stub, None) == ["description is required"], \
        "text mode must still catch the dominant defect"

    res, _ = _run(monkeypatch, tmp_path, {"devops/good": GOOD})
    statuses = _statuses(res)
    assert "PASS" not in statuses, "a degraded run must never report a PASS"
    assert "FAIL" not in statuses, "a missing library is not the file's fault"
    assert "WARN" in statuses
    assert any("TEXT mode" in c["detail"] for c in res.checks)


def test_text_mode_states_which_rules_it_did_not_apply(tmp_path):
    """The degradation is REPORTED, never silent — and the gap is real.

    Name charset and YAML-parse errors are NOT covered in text mode. Pinned so a
    later reader cannot mistake the text scan for the full rule set.
    """
    p = _skill(tmp_path, "productivity/here-now",
               "---\nname: here.now\ndescription: Publish sites.\n---\n\n# H\n")
    assert _defects(p, None) == [], "text mode cannot see the charset rule"
    assert any("invalid characters" in d for d in _defects(p, yaml))


def test_check_is_read_only(monkeypatch, tmp_path):
    """A verifier must not mutate the thing it measures."""
    _, repo = _run(monkeypatch, tmp_path, {"devops/good": GOOD})
    before = sorted(p.relative_to(repo) for p in repo.rglob("*"))
    res = Results()
    checks.check_skills_loadable(res)
    after = sorted(p.relative_to(repo) for p in repo.rglob("*"))
    assert before == after
