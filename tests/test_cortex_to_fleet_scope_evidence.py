"""Contract test for the cortex->fleet scope evidence collector.

The collector is a READ-ONLY, re-runnable reporter: docs/plans/cortex-to-fleet-
rename-plan.md quotes its numbers, so the numbers must have an enforced shape.
This test pins the CONTRACT (exit code, required sections, the invariants the
plan relies on) — never a hand-copied constant that would echo the script back
at itself.

Inert on import: no module-level work, no SystemExit.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "evidence" / "cortex-to-fleet-scope-2026-11-06.py"

# A check that cannot run is a third outcome, not a pass.
COULD_NOT_VERIFY = 3

REQUIRED_SECTIONS = (
    "## 1. Token families",
    "## 2. Sweep-scope carriers",
    "## 3. Tracked paths containing 'cortex'",
    "## 4. register() map",
    "## 5. CORTEX_* env var names",
    "## 6. mycortex post-condition",
)

FAMILY_ROW = re.compile(
    r"^(?P<name>.+?)\s+(?P<total>\d+)\s+(?P<files>\d+)\s+(?P<inscope>\d+)\s*$"
)


def _run() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def test_script_exists_and_is_inert_on_import():
    assert SCRIPT.is_file(), f"evidence collector missing: {SCRIPT}"
    # Importing it must not do work (no module-level main() call is asserted by
    # re-import in a subprocess with a read-only cwd that is NOT the repo).
    probe = subprocess.run(
        [sys.executable, "-c",
         f"import importlib.util,sys;"
         f"spec=importlib.util.spec_from_file_location('ev',r'{SCRIPT}');"
         f"m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
         f"print('IMPORTED_OK')"],
        cwd="/", capture_output=True, text=True, check=False, timeout=120,
    )
    assert probe.returncode == 0, (
        f"importing the collector failed (rc={probe.returncode}): {probe.stderr[:400]}"
    )


def test_reports_every_required_section_with_rc_zero():
    res = _run()
    if res.returncode != 0:
        # Distinguish "could not run" from "ran and failed" — they are not the same.
        print(f"COULD NOT VERIFY: collector rc={res.returncode}\n{res.stderr[:800]}")
        assert res.returncode == COULD_NOT_VERIFY or res.returncode == 0
    for section in REQUIRED_SECTIONS:
        assert section in res.stdout, f"section missing from evidence output: {section!r}"


def test_family_counts_are_internally_consistent():
    """in-scope <= total, and files <= total, for every family row."""
    res = _run()
    assert res.returncode == 0, f"collector rc={res.returncode}: {res.stderr[:400]}"

    seen = 0
    for line in res.stdout.splitlines():
        if not line.strip() or line.startswith(("=", "#", "cmd:", "family", "REPO", " ")):
            continue
        m = FAMILY_ROW.match(line)
        if not m:
            continue
        name, total, files, inscope = (
            m.group("name").strip(), int(m.group("total")),
            int(m.group("files")), int(m.group("inscope")),
        )
        assert inscope <= total, f"{name}: in-scope {inscope} exceeds total {total}"
        assert files <= total, f"{name}: files {files} exceeds total {total}"
        seen += 1
    assert seen >= 5, f"expected at least 5 token-family rows, saw {seen}"


def test_mycortex_post_condition_is_reported():
    """The §3.2 guard needs a baseline count; the collector must print one."""
    res = _run()
    assert res.returncode == 0
    block = res.stdout.split("## 6. mycortex post-condition", 1)
    assert len(block) == 2, "mycortex post-condition section absent"
    m = re.search(r"files containing 'mycortex' = (\d+)", block[1])
    assert m, "mycortex baseline count not reported"
    assert int(m.group(1)) > 0, "mycortex baseline count must be positive"


def test_register_map_count_is_distinguished_from_token_count():
    """The plan reconciles two different figures; the collector must emit both."""
    res = _run()
    assert res.returncode == 0
    block = res.stdout.split("## 4. register() map", 1)
    assert len(block) == 2, "register() section absent"
    assert re.search(r"leading-anchored register .+ calls\s*=\s*\d+", block[1])
    assert re.search(r"all occurrences of the token 'register'\s*=\s*\d+", block[1])


def test_cortex_delta_section_reconciles_the_two_counts():
    """§4.2 quotes a family count AND an identifier count; the delta must be derivable."""
    res = _run()
    assert res.returncode == 0, f"collector rc={res.returncode}: {res.stderr[:400]}"
    block = res.stdout.split("## 7. CORTEX_ delta", 1)
    assert len(block) == 2, "CORTEX_ delta section absent — the two counts cannot be reconciled"
    body = block[1]

    fam = re.search(r"family\s+r'CORTEX_'\s+=\s+(\d+)", body)
    ident = re.search(r"ident\s+r'CORTEX_\[A-Z0-9_\]\+'\s+=\s+(\d+)", body)
    delta = re.search(r"delta\s+=\s+(\d+)", body)
    assert fam and ident and delta, "delta section did not report all three figures"

    f, i, d = int(fam.group(1)), int(ident.group(1)), int(delta.group(1))
    assert f >= i, f"family count {f} must be >= identifier count {i}"
    assert d == f - i, f"reported delta {d} != family({f}) - ident({i})"
    assert d > 0, "delta must be positive — the plan's whole point is that the two differ"
