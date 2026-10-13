"""The review verdict is keyed on the ARTIFACT, not on the worker's note.

Why this is the cost fix. One cycle in this session paid for 8+ reviews whose diff never moved
between them: every retry explained itself differently, and the fingerprint covered the whole
material — so each new paragraph bought a fresh judgment of an unchanged artifact. That is the most
expensive way to change nothing.

What must stay true: the note is still IN the material the reviewer reads (it is a self-report to be
checked against the diff, not something to hide), and rereview_change(force=True) remains the
explicit re-judge when the note itself is the thing that changed.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"


def _load():
    spec = importlib.util.spec_from_file_location("gov_fp", MCP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gov_fp"] = mod
    spec.loader.exec_module(mod)
    return mod


def _parts(**over):
    base = {
        "sid": "test-session",
        "author": "the-agent",
        "repo": "/repo",
        "branch": "main",
        "head_sha": "abc123",
        "base": "def456",
        "range_note": "(commits authored by the agent above)",
        "cycle_id": 999,
        "task_id": "delta-review-fingerprint",
        "description": "key the verdict on the artifact",
        "scope": {
            "files": 3,
            "lines": 120,
            "always_paths": [],
            "numstat": "40\t4\tmcp-servers/loop-gov-mcp.py",
        },
        "excluded_note": "",
        "note": "first wording of the same story",
        "diff_text": "+def f():\n+    return 1\n",
    }
    base.update(over)
    return base


def test_a_reworded_note_does_not_buy_a_fresh_review():
    """THE SAVING: same artifact, different note -> same key -> the stored verdict is reused."""
    mod = _load()
    material_a, key_a = mod._build_review_material(_parts(note="first wording"))
    material_b, key_b = mod._build_review_material(
        _parts(note="a much longer retelling of exactly the same diff, with more evidence cited")
    )
    assert material_a != material_b, "the note must still reach the reviewer — it is material to read"
    assert key_a == key_b, "but it must not re-open judgment of an unchanged artifact"


def test_a_changed_diff_is_always_a_new_review():
    mod = _load()
    _, key_a = mod._build_review_material(_parts())
    _, key_b = mod._build_review_material(_parts(diff_text="+def g():\n+    return 2\n"))
    assert key_a != key_b, "a different diff is a different artifact"


def test_the_ranges_head_and_scope_stay_in_the_key():
    """The key must not become so narrow that a genuinely different change reuses a verdict."""
    mod = _load()
    _, key_a = mod._build_review_material(_parts())
    for field, value in (
        ("head_sha", "999999"),
        ("base", "000000"),
        ("range_note", "(UNNARROWED — session identity unresolved)"),
        ("description", "a different task entirely"),
        ("task_id", "other-task"),
        ("scope", {"files": 40, "lines": 900, "always_paths": ["mcp-servers/"], "numstat": "900\t0\tx"}),
        ("excluded_note", "...[OUT OF SCOPE: working-tree changes]"),
    ):
        _, key_b = mod._build_review_material(_parts(**{field: value}))
        assert key_a != key_b, f"changing {field} must invalidate the stored verdict"


def test_the_note_and_the_diff_both_reach_the_reviewer():
    mod = _load()
    material, artifact = mod._build_review_material(_parts())
    assert "first wording" in material, "the note is the self-report the reviewer checks"
    assert "+def f():" in material, "and the diff is what it checks it against"
    assert "+def f():" in artifact, "the artifact carries the diff itself"
    assert "Worker's note" not in artifact, "the artifact key has no commentary in it"