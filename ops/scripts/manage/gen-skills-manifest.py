#!/usr/bin/env python3
"""Generate docs/SKILLS-MANIFEST.md from skills/ — single source of truth.

The manifest is a derived artifact. Hand-maintaining it drifts (286 skills in
repo vs 29 listed, 2026-08-04). This generator rebuilds the category tables
from skills/**/SKILL.md frontmatter, preserving the hand-written tail
(Infrastructure Scripts, Naming Convention, Notes, Version History).

Usage:
  gen-skills-manifest.py            # regenerate docs/SKILLS-MANIFEST.md
  gen-skills-manifest.py --check    # exit 1 if file would change (audit gate)

Registered in cortex-update.sh + wired into pre-commit-doc-audit.sh Check 2
as the freshness gate: any staged skills/ change triggers --check.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent.parent  # hermes-cortex/
SKILLS_DIR = REPO / "skills"
MANIFEST = REPO / "docs" / "SKILLS-MANIFEST.md"

HEADER = """# Skills Manifest — Hermes Cortex

Skills in this repo auto-install via `install.sh` step 10, which
recursively copies `skills/` to `~/.hermes/skills/`, preserving category
subdirectories. Skills are distributed across multiple categories matching
their domain.

> **AUTO-GENERATED FILE — do not edit by hand.** Regenerate with:
> `python3 ops/scripts/manage/gen-skills-manifest.py`
> The pre-commit doc audit runs `--check` whenever skills/ changes.

"""

# Sections preserved verbatim from the previous file (hand-written tail).
PRESERVE_MARKERS = ("## Infrastructure Scripts", "## Naming Convention",
                    "## Notes", "## Version History")


def _humanize(cat: str) -> str:
    """software-development -> Software Development; github -> GitHub."""
    words = [w.capitalize() for w in re.split(r"[_-]", cat) if w]
    name = " ".join(words)
    return {"Github": "GitHub"}.get(name, name)


def _load_skills() -> dict[str, list[dict]]:
    """Scan skills/ for SKILL.md — recursive, any depth:

    - skills/<category>/<name>/SKILL.md  (categorized)
    - skills/<category>/<sub>/<name>/SKILL.md  (nested: mlops/inference/...)
    - skills/<name>/SKILL.md             (flat, top-level)

    Hidden dirs (.archive) are skipped. Each skill is categorized under its
    TOP-LEVEL dir name. Returns {category: [skills]}.
    """
    cats: dict[str, list[dict]] = {}
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        cat_name = _humanize(entry.name)
        # Flat layout: skills/<name>/SKILL.md
        flat = entry / "SKILL.md"
        if flat.is_file():
            fm = _frontmatter(flat)
            if fm:
                cats.setdefault(cat_name, []).append({
                    "name": fm.get("name", entry.name),
                    "version": fm.get("version", "1.0.0"),
                    "desc": _short_desc(fm.get("description", "")),
                })
            continue
        # Categorized/nested layout — recurse for SKILL.md under the category
        for f in sorted(entry.rglob("SKILL.md")):
            fm = _frontmatter(f)
            if not fm:
                continue
            skill_dir = f.parent
            cats.setdefault(cat_name, []).append({
                "name": fm.get("name", skill_dir.name),
                "version": fm.get("version", "1.0.0"),
                "desc": _short_desc(fm.get("description", "")),
            })
    return cats


def _frontmatter(path: Path) -> dict | None:
    """Parse YAML frontmatter; return dict or None."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _short_desc(desc: str) -> str:
    """First line, ~110 chars, ellipsis. Handles quoted/multiline YAML."""
    if not desc:
        return "(no description)"
    first = str(desc).strip().splitlines()[0]
    if len(first) > 110:
        first = first[:107].rstrip() + "..."
    return first.replace("|", "\\|")


def _render(cats: dict[str, list[dict]], preserved_tail: str) -> str:
    out = [HEADER]
    for cat in sorted(cats):
        skills = sorted(cats[cat], key=lambda s: s["name"])
        out.append(f"## {cat} ({len(skills)} skill{'s' if len(skills) != 1 else ''})\n")
        out.append("| Skill | Version | Purpose | Load With |")
        out.append("|-------|---------|---------|-----------|")
        for s in skills:
            out.append(f"| `{s['name']}` | {s['version']} | {s['desc']} | "
                       f"`skill_view(name='{s['name']}')` |")
        out.append("")
    if preserved_tail:
        out.append(preserved_tail)
    return "\n".join(out).rstrip() + "\n"


def _extract_tail(text: str) -> str:
    """Keep everything from the first PRESERVE_MARKERS heading onward."""
    for marker in PRESERVE_MARKERS:
        idx = text.find(f"## {marker.removeprefix('## ')}")
        if idx == -1:
            idx = text.find(marker)
        if idx != -1:
            return text[idx:].rstrip() + "\n"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the manifest is stale (audit gate)")
    args = ap.parse_args()

    cats = _load_skills()
    old = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
    new = _render(cats, _extract_tail(old))

    if new == old:
        print(f"✓ SKILLS-MANIFEST.md fresh ({sum(len(v) for v in cats.values())} skills)")
        return 0
    if args.check:
        print(f"❌ SKILLS-MANIFEST.md stale — run: "
              f"python3 ops/scripts/manage/gen-skills-manifest.py", file=sys.stderr)
        return 1
    MANIFEST.write_text(new, encoding="utf-8")
    print(f"✓ Regenerated SKILLS-MANIFEST.md "
          f"({sum(len(v) for v in cats.values())} skills, "
          f"{len(cats)} categories)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
