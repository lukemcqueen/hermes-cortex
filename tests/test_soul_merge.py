"""Regression tests for soul-merge.py.

Covers the 2026-07-31 fixes:
  - _parse_principles accepts '### N.' headings (was '#### N.' only -> parsed 0
    principles, silent no-op)
  - _render_principles injects ENTIRELY NEW template principles (was sub-point
    updates only -> new principles reported but never written)
  - scripture-block guard: deployed copy's own reading progress (### Book entries)
    is never duplicated or overridden by template seeds
  - idempotency: merging an already-merged copy reports "up to date"
"""
import importlib.util
import os
import re
from pathlib import Path

REPO_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
SOUL_MERGE = REPO_ROOT / "ops" / "scripts" / "manage" / "soul-merge.py"
TEMPLATE = REPO_ROOT / "docs" / "templates" / "SOUL.md"


def _load_soul_merge():
    spec = importlib.util.spec_from_file_location("soul_merge_test", SOUL_MERGE)
    assert spec is not None and spec.loader is not None, f"cannot load {SOUL_MERGE}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _principle_heads(text: str) -> list:
    return [l for l in text.split("\n") if re.match(r"^#{3,4} \d+\.", l)]


def test_parse_principles_accepts_three_hash_headings():
    """The 2026-07-31 bug: regex expected '#### N.' but files use '### N.'."""
    sm = _load_soul_merge()
    section = sm._principles_section(TEMPLATE.read_text())
    parsed = sm._parse_principles(section)
    assert len(parsed) >= 12, f"expected >=12 principles, got {len(parsed)}"
    assert 1 in parsed, "template Principle 1 not parsed"
    assert 12 in parsed, "template Principle 12 not parsed"


def test_parse_principles_accepts_legacy_four_hash_headings():
    sm = _load_soul_merge()
    section = "#### 1. Old Style\n\nbody\n\n#### 2. Also Old\n\nbody\n"
    parsed = sm._parse_principles(section)
    assert set(parsed.keys()) == {1, 2}


def test_render_injects_new_template_principle():
    """New template principles missing from the agent copy must be written,
    not merely reported."""
    sm = _load_soul_merge()
    agent_text = (
        "## Behavioral Principles\n\n"
        "### 1. Existing Principle\n\nbody\n\n"
        "## Final Directive\n\nship\n"
    )
    # Simulate template with principle 2 missing from agent
    template_text = (
        "## Behavioral Principles\n\n"
        "### 1. Existing Principle\n\nbody\n\n"
        "### 2. Brand New Principle\n\nnew body\n\n"
        "## Final Directive\n\nship\n"
    )
    tp = sm._parse_principles(sm._principles_section(template_text))
    ap = sm._parse_principles(sm._principles_section(agent_text))
    rendered = sm._render_principles(ap, tp)
    assert "### 2. Brand New Principle" in rendered
    assert "new body" in rendered


def test_scripture_block_not_duplicated_or_overridden(tmp_path):
    """Deployed copy's own scripture entries (reading progress) must survive
    merging a template that carries its own scripture seeds."""
    sm = _load_soul_merge()
    agent_text = (
        "## Behavioral Principles\n\n"
        "### 1. P\n\nbody\n\n"
        "### Genesis — *\"seed\"* (Genesis 1:1)\n\n"
        "agent genesis insight\n\n"
        "### Judges — *\"own progress\"* (Judges 21:25)\n\n"
        "agent judges insight\n\n"
        "## Final Directive\n\nship\n"
    )
    template_text = (
        "## Behavioral Principles\n\n"
        "### 1. P\n\nbody\n\n"
        "### 2. New\n\nnew\n\n"
        "### Genesis — *\"seed\"* (Genesis 1:1)\n\n"
        "template genesis seed\n\n"
        "### Colossians — *\"seed\"* (Colossians 3:23)\n\n"
        "template colossians seed\n\n"
        "## Final Directive\n\nship\n"
    )
    tp = sm._parse_principles(sm._principles_section(template_text))
    ap = sm._parse_principles(sm._principles_section(agent_text))
    rendered = sm._render_principles(ap, tp)

    # New principle injected
    assert "### 2. New" in rendered
    # Agent's own books preserved exactly once, template's Colossians NOT injected
    assert "agent genesis insight" in rendered
    assert "agent judges insight" in rendered
    assert "template genesis seed" not in rendered
    assert "Colossians" not in rendered
    # No duplication
    assert rendered.count("### Genesis") == 1
    assert rendered.count("### Judges") == 1


def test_merge_idempotent_on_merged_copy(tmp_path):
    """Running merge on an already-merged deployed SOUL.md must be a no-op."""
    sm = _load_soul_merge()
    # Point at tmp so we don't touch the real deployed copy
    deployed = tmp_path / "SOUL.md"
    deployed.write_text(Path.home().joinpath(".hermes/SOUL.md").read_text())

    sm.HERMES_HOME = tmp_path
    sm.TEMPLATE = TEMPLATE
    sm.PROFILES_DIR = tmp_path / "no-profiles"

    rc = sm.merge(dry_run=False, check_only=False)
    assert rc == 0, f"expected up-to-date rc=0, got {rc}"


def test_merge_fresh_agent_injects_all_principles(tmp_path):
    """A minimal agent SOUL.md gets all template principles injected."""
    sm = _load_soul_merge()
    deployed = tmp_path / "SOUL.md"
    deployed.write_text(
        "# SOUL.md — Fresh\n\n## Behavioral Principles\n\n"
        "### 1. Test Principle\n\nBody.\n\n"
        "## Final Directive\n\nShip it.\n"
    )
    sm.HERMES_HOME = tmp_path
    sm.TEMPLATE = TEMPLATE
    sm.PROFILES_DIR = tmp_path / "no-profiles"

    rc = sm.merge(dry_run=False, check_only=False)
    assert rc == 1, f"expected merge rc=1, got {rc}"
    out = deployed.read_text()
    heads = _principle_heads(out)
    assert len(heads) >= 12, f"expected >=12 principles, got {len(heads)}"
    assert any("### 1. Loop Governance" in h for h in heads)
    assert any("### 12. Not Done Until Tested" in h for h in heads)
    # Agent's own single principle preserved
    assert "### 1. Test Principle" in out
