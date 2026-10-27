#!/usr/bin/env python3
"""The enforcer's read-only allowlist must cover the brain's QUERY subcommands.

Measured 2026-10-27 by importing the shipped classifier: `mycortex list`,
`search`, `stats` and `doctor` all returned readonly=False, while `ls`,
`grep` and `git status` returned True. A write-class verdict demands a
governance lock, so the unattended nightly dream could not even READ the brain
— it died on its first step and wrote nothing (job ad77f951f753 / 6cb3c26a2ac9,
[CRON_FAILURE] every night).

Both directions are pinned. Widening a classifier to admit reads is only safe
if the MUTATING siblings stay refused: `mycortex sync` writes the index,
`sources add|remove` changes registration, and `answer store|prune` writes the
cache. A test that only proved the reads became read-only would pass just as
happily against an allowlist that had been widened to `mycortex .*`.

Run: bash tests/run-tests.sh tests/test_enforcer_mycortex_readonly.py -q
"""

import importlib.util
import os
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
ENFORCER = REPO / "plugins" / "governance-enforcer" / "__init__.py"

# Read-only by intent — query the index, never change it.
READS = [
    "mycortex list -n 20",
    'mycortex search "dream layer" --limit 3',
    "mycortex search connection --source hermes-cortex",
    "mycortex stats",
    "mycortex stats --json",
    "mycortex doctor",
    "mycortex doctor --json",
    "mycortex sources list",
    "mycortex sources list --json",
    "mycortex answer search \"how do we deploy\"",
    "mycortex answer stats",
]

# Mutations — must stay write-class (a lock is required to run these).
MUTATIONS = [
    "mycortex sync",
    "mycortex sync --source esther",
    "mycortex sources add foo /tmp/foo",
    "mycortex sources remove foo",
    "mycortex answer store \"q\" \"a\"",
    "mycortex answer prune",
    "mycortex sync && mycortex list",
    "mycortex list; mycortex sync",
]


def _classifier():
    """The SHIPPED predicate, imported from the repo source — never a re-implementation.

    Skips (never fails) when the module cannot be loaded here: a missing
    dependency is a could-not-verify, not a defect in the artifact under test.
    """
    if not ENFORCER.is_file():
        pytest.skip(f"enforcer source not present at {ENFORCER}")
    spec = importlib.util.spec_from_file_location("enf_mycortex_probe", ENFORCER)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 — surface why, do not silently pass
        pytest.skip(f"could not import the enforcer: {type(e).__name__}: {e}")
    fn = getattr(mod, "_is_readonly_terminal_command", None)
    if fn is None:
        pytest.fail("enforcer exposes no _is_readonly_terminal_command — the predicate moved")
    return fn


def test_the_predicate_is_reachable():
    """Guard against a vacuous run: assert we can actually call the subject."""
    fn = _classifier()
    assert fn("ls") is True, "sanity: a known read primitive must classify read-only"


@pytest.mark.parametrize("cmd", READS)
def test_brain_query_subcommands_are_read_only(cmd):
    fn = _classifier()
    assert fn(cmd) is True, (
        f"{cmd!r} is classified WRITE-class, so an unattended session cannot run it "
        "without holding a governance lock — this is the nightly dream's first step"
    )


@pytest.mark.parametrize("cmd", MUTATIONS)
def test_brain_mutations_stay_write_class(cmd):
    fn = _classifier()
    assert fn(cmd) is False, (
        f"{cmd!r} is classified read-only but it MUTATES the brain — widening the "
        "allowlist must never admit these"
    )


def test_every_mycortex_allowlist_line_is_subcommand_scoped():
    """Source guard: the plausible wrong fix is a whole-CLI entry.

    An entry like `^\\s*(mycortex)\\b` would admit `sync` too. Slice by LINE —
    slicing the block at the first `]` lands inside `[vV]` of an earlier
    pattern and reports a truncated block (this probe failed that way first).
    """
    src = ENFORCER.read_text(encoding="utf-8")
    lines = [ln for ln in src.splitlines()
             if "mycortex" in ln and ln.strip().startswith(("r\"", "r'"))]
    assert lines, "no mycortex entry in the read-only allowlist"
    for ln in lines:
        # Match the CONSTRUCT as written in the source: the file holds the
        # literal characters `\s`, not whitespace, so a runtime-style regex
        # here reports every correct line as a violation.
        assert r"(mycortex)\s+" in ln, \
            f"allowlist line grants the whole CLI, not a subcommand: {ln.strip()}"
    print(f"  {len(lines)} mycortex allowlist line(s), all subcommand-scoped ✓")
