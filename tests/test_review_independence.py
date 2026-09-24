"""Story M6.4 — the independence guarantee (CHECK).

Verifies with real assertions, not claims:
(a) the prompt template lives in an orchestrator-only path (docs/templates/
    is listed in docs/orchestrator-only-paths.txt);
(b) the reviewer script reads the prompt ONLY from the committed template
    (never from worker-authored input other than the appended material);
(c) the reviewed material is appended strictly BELOW the untrusted marker.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "docs" / "templates" / "adversarial-reviewer-prompt.md"
ORCH_PATHS = REPO / "docs" / "orchestrator-only-paths.txt"
REVIEW = REPO / "ops" / "scripts" / "orch-bus" / "adversarial-review.py"


def test_template_is_under_an_orchestrator_only_path():
    assert ORCH_PATHS.exists(), "orchestrator-only-paths.txt missing"
    text = ORCH_PATHS.read_text()
    assert "docs/templates" in text, (
        "docs/templates is not declared orchestrator-only — the worker could "
        "edit the reviewer's constitution"
    )


def test_reviewer_script_reads_prompt_from_committed_template_only():
    src = REVIEW.read_text()
    # The template path must be a constant pointing at docs/templates/.
    assert re.search(
        r'TEMPLATE\s*=\s*REPO\s*/\s*["\']docs["\']\s*/\s*["\']templates["\']'
        r'\s*/\s*["\']adversarial-reviewer-prompt\.md["\']',
        src,
    ), "reviewer script does not pin the committed template path"
    # The ONLY file read feeding the prompt is the committed template.
    # (assemble_prompt must contain the sole read_text() that touches the
    # prompt; other reads in the script are env/db, never prompt input.)
    asm_start = src.find("def assemble_prompt")
    asm_end = src.find("\ndef ", asm_start + 1)
    asm = src[asm_start:asm_end]
    assert "TEMPLATE.read_text()" in asm, "assemble_prompt must read the template"
    assert asm.count(".read_text()") == 1, (
        "assemble_prompt reads something besides the committed template — "
        "worker-authored text could become instructions"
    )


def test_material_is_appended_below_the_marker():
    src = REVIEW.read_text()
    marker_pos = src.find('MARKER = "=== REVIEWED MATERIAL ==="')
    assemble_pos = src.find("def assemble_prompt")
    assert marker_pos != -1 and assemble_pos != -1
    assert marker_pos < assemble_pos
    # The f-string must place the template FIRST and the material AFTER.
    assert 'f"{template}\\n{material}\\n"' in src, (
        "prompt assembly must be template-then-material (material below the "
        "untrusted marker, never above it)"
    )
