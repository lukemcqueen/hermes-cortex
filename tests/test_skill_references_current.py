"""Guard: skill files must not point agents at deprecated skills.

Two reference classes decay silently and both cost real turns:

  * a backticked NAME in prose (`server-administration`) — the agent loads it, gets
    a tombstone, and loads the real skill second. Found 14 of these across the
    fleet on 2026-10-22, including two in the always-loaded survey-before-action
    routing table, which is the worst place for one: the table exists to make the
    first load the right one.
  * a `related_skills` frontmatter entry naming a stub.

Both checks are CLOSED-SET matches against the names that actually carry
`deprecated: true`, so they cannot fire on prose that merely looks like a skill
name. That matters: a guard that cries wolf gets ignored, and a first draft of
this class of check was measured at 886 false failures because it matched any
path-shaped token. Precision is the feature.
"""
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SCANNED_SUFFIXES = (".md",)


def _frontmatter(path):
    text = path.read_text(errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def _related(fm):
    """`related_skills` wherever it lives: top level or metadata.hermes."""
    out = list(fm.get("related_skills") or [])
    meta = fm.get("metadata")
    if isinstance(meta, dict):
        hermes = meta.get("hermes")
        if isinstance(hermes, dict):
            out += list(hermes.get("related_skills") or [])
    return [r for r in out if isinstance(r, str)]


def _skill_files():
    return sorted(p for p in SKILLS.rglob("*")
                  if p.suffix in SCANNED_SUFFIXES and p.is_file()
                  and ".archive" not in p.parts)


def _stub_map():
    """name -> absorbed_into, for every live stub carrying `deprecated: true`."""
    stubs, live = {}, set()
    for p in SKILLS.rglob("SKILL.md"):
        if ".archive" in p.parts:
            continue
        fm = _frontmatter(p)
        name = fm.get("name")
        if not isinstance(name, str):
            continue
        if fm.get("deprecated"):
            stubs[name] = p
        else:
            live.add(name)
    return stubs, live


def find_deprecated_refs(root, stubs, live):
    """[(file, line, name)] for backticked references to a deprecated skill name."""
    hits = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in SCANNED_SUFFIXES or ".archive" in p.parts:
            continue
        text = p.read_text(errors="replace")
        for name in stubs:
            if name in live:
                continue  # a live skill that also declares deprecated is not a stub
            for m in re.finditer(r"`" + re.escape(name) + r"`", text):
                hits.append((str(p), text[: m.start()].count("\n") + 1, name))
    return hits


def find_stub_redirects(root, stubs, live):
    """[(file, entry)] for `related_skills` entries naming a deprecated stub."""
    hits = []
    for p in sorted(root.rglob("SKILL.md")):
        if ".archive" in p.parts:
            continue
        for entry in _related(_frontmatter(p)):
            if entry in stubs and entry not in live:
                hits.append((str(p), entry))
    return hits


STUBS, LIVE = _stub_map()


def test_the_scan_has_something_to_scan():
    """A guard that silently examines nothing passes for the wrong reason."""
    assert len(LIVE) > 200, f"only {len(LIVE)} live skills found — is SKILLS pointing at the tree?"
    assert STUBS, "no deprecated stubs found — the stub map is empty, so both checks are vacuous"


def test_every_stub_declares_its_redirect():
    """The redirect is what makes 'fix the reference' mechanical rather than a judgement call."""
    missing = [n for n, p in STUBS.items()
               if not (_frontmatter(p).get("absorbed_into") or _frontmatter(p).get("replaced_by"))]
    assert not missing, (
        f"deprecated stub(s) with no absorbed_into/replaced_by: {missing} — "
        "a reference to these cannot be redirected automatically"
    )


def test_no_skill_references_a_deprecated_name():
    hits = find_deprecated_refs(SKILLS, STUBS, LIVE)
    if hits:
        lines = "\n".join(
            f"  {Path(f).relative_to(REPO)}:{ln}  `{name}` -> merge into "
            f"{_frontmatter(STUBS[name]).get('absorbed_into')}"
            for f, ln, name in hits
        )
        pytest.fail(f"{len(hits)} reference(s) to DEPRECATED skill names:\n{lines}")


def test_no_related_skills_entry_points_at_a_stub():
    hits = find_stub_redirects(SKILLS, STUBS, LIVE)
    assert not hits, (
        "related_skills entries naming a deprecated stub "
        f"(rewrite to the absorbed_into target): {hits}"
    )


def test_the_scanners_actually_discriminate(tmp_path):
    """Both scanners must FLAG a planted reference, or the green above proves nothing."""
    planted = tmp_path / "skills" / "some-skill"
    planted.mkdir(parents=True)
    stub_name = next(iter(STUBS))
    (planted / "SKILL.md").write_text(
        f"---\nname: some-skill\nrelated_skills: [{stub_name}]\n---\n\n"
        f"Use `{stub_name}` for this.\n"
    )
    assert find_deprecated_refs(tmp_path / "skills", STUBS, LIVE), \
        "the prose scanner did not flag a planted deprecated reference"
    assert find_stub_redirects(tmp_path / "skills", STUBS, LIVE), \
        "the related_skills scanner did not flag a planted stub entry"


def test_a_live_name_is_never_flagged(tmp_path):
    """The other direction: a real, live skill name must pass."""
    planted = tmp_path / "skills" / "some-skill"
    planted.mkdir(parents=True)
    live_name = sorted(LIVE)[0]
    (planted / "SKILL.md").write_text(
        f"---\nname: some-skill\nrelated_skills: [{live_name}]\n---\n\n"
        f"Use `{live_name}` for this.\n"
    )
    assert not find_deprecated_refs(tmp_path / "skills", STUBS, LIVE)
    assert not find_stub_redirects(tmp_path / "skills", STUBS, LIVE)
