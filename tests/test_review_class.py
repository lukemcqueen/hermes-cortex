#!/usr/bin/env python3
"""E0 — `_review_class()` is a PURE risk classifier with inert wiring (PLAN ONLY).

docs/design/review-risk-routing.md lever E: the close gate is size-triggered today
(`_complexity` l.5224, 50-line/3-file thresholds, skip at l.7080) and its depth tiers
no longer change who judges (`_tier` l.5447, `_light_reviewer_model` l.5424-5444), so
every non-trivial close pays pro. `_review_class(paths, ...)` replaces the size test
with a RISK class computed FROM THE DIFF's file set — never from a note.

Class contract (plan §2/§3):
  A0 deterministic-only — every non-noise path is documentation, no always-review path,
     no protected surface, range non-empty, no uncommitted-code claim. No model judge.
  B  cheap judge — a code change WITH a test delta, no always-review, no protected.
  C  deep judge — everything else, fail-closed: protected surface, no-test code, an
     empty or unparseable path set, an unresolved identity.

Fail-closed rules pinned here (plan §3): unknown/empty -> C; always-review or protected
path -> C regardless; uncommitted-code claim -> C; a class never comes from the note.

Run: python3 -m pytest tests/test_review_class.py -v   (no repo/git needed — pure).
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"

spec = importlib.util.spec_from_file_location("loop_gov_mcp", MCP)
if spec and spec.loader:
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)
else:
    raise AssertionError(f"cannot load {MCP}")

A0 = "A0"
B = "B"
C = "C"
DOCS = ["docs/design/review-risk-routing.md", "docs/research/review-cost-advisory-chatgpt-2026-10-29.md"]
EVIDENCE = ["docs/evidence/fleet-update-verify-2026-10-29.md", "docs/evidence/run-output.txt"]
CODE = ["ops/scripts/tool.py"]
CODE_WITH_TEST = ["ops/scripts/tool.py", "tests/test_tool.py"]
ALWAYS = ["mcp-servers/loop-gov-mcp.py"]
ALWAYS_MD = ["plugins/governance-enforcer/__init__.md"]  # .md but ALWAYS_REVIEW -> never A0
PROTECTED = ["ops/install/hooks/pre-commit", "migrations/0001_xxx.py", "gateway/gateway.yaml",
             "ops/install/deploy/nginx/x.conf"]
LOCKFILE_ONLY = ["Cargo.lock"]


@pytest.mark.parametrize("paths,expected", [
    (DOCS, A0),                                   # pure prose
    (EVIDENCE, A0),                               # docs/evidence any suffix
    (["docs/README.md"], A0),                     # single doc
    (CODE_WITH_TEST, B),                          # code + test delta
    (["ops/scripts/tool.py", "docs/x.md", "tests/test_tool.py"], B),  # code+docs+test
    ([], C),                                      # empty -> fail closed
    (LOCKFILE_ONLY, C),                           # only noise/lockfile -> not classifiable, C
    (CODE, C),                                    # code with NO test -> C
    (ALWAYS, C),                                 # enforcement surface -> deep
    (ALWAYS_MD, C),                              # always-review even with .md suffix
    ([p for p in PROTECTED] + ["tests/test_x.py"], C),  # protected + test still C
    ([DOCS[0], CODE[0]], C),                     # docs + untested code -> C
], ids=lambda v: v)
def test_review_class_deterministic(paths, expected):
    """The pure classifier answers the same way for every input (no ambient state)."""
    assert hc._review_class(list(paths)) == expected


def test_has_uncommitted_code_forces_C_even_for_docs():
    """Plan §3 rule 4: an uncommitted-code claim is never A0."""
    assert hc._review_class(DOCS, has_uncommitted_code=True) == C