#!/usr/bin/env python3
"""Re-runnable verifier: canonical UUIDs are not phone numbers.

Read-only. Nothing here writes governance state, the store, or the repo: it
loads BOTH enforcer revisions in one process (the pre-fix revision extracted
from git, and the deployment copy named by MODPATH) and runs the same inputs
through each, which is the differential probe enforcement-change-safety Rule 23
asks for.

  MODPATH=<enforcer __init__.py under test>  python3 probe.py

Output is captured verbatim into transcript.txt beside this file. Volatile by
design: the pytest duration line (normalised to <t>).
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import random
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TARGET_TEST = REPO / "tests" / "test_enforcer_pii_gate.py"

# The revision BEFORE the UUID narrowing. Pinned by SHA, never 'HEAD': the fix
# lands in the same commit as this probe, so HEAD would resolve to the fixed
# module and the before/after would be a tautology.
PRE_FIX_REV = "4764289b"

SAMPLES = 20000          # gate-level samples (decisive property)
REGEX_SAMPLES = 200000   # regex-level samples (the reported rate)


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f"enf_{path.stem}_{abs(hash(str(path)))%10**6}", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prev_module():
    out = subprocess.run(
        ["git", "-C", str(REPO), "show",
         f"{PRE_FIX_REV}:plugins/governance-enforcer/__init__.py"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(f"CANNOT VERIFY: git show {PRE_FIX_REV} failed: {out.stderr.strip()}")
    p = Path(tempfile.mkdtemp()) / "enforcer_pre_fix.py"
    p.write_text(out.stdout, encoding="utf-8")
    return load(p)


def gate(mod, text: str) -> bool:
    """True = the gate refuses the write (the PII path fires)."""
    args = {"path": str(REPO / "docs" / "probe-target.md"), "content": text}
    return mod._check_pii_content_gate("write_file", args) is not None


def _handles(values: list[str]) -> str:
    """sha256 handles, a few chars each: this transcript is a PUBLIC file and
    must not restate the shapes its own gate refuses."""
    if not values:
        return "-"
    return ",".join(sorted(hashlib.sha256(v.encode()).hexdigest()[:8] for v in values))


def _red(value) -> str:
    """Redact host paths at the generator: a transcript committed to the public
    repo must not carry /home/<user> (change-checklist, Phase 1.5)."""
    return re.sub(r"/home/[A-Za-z0-9._-]+", "$HOME", str(value))


def main() -> int:
    newpath = Path(os.environ.get("MODPATH") or
                   REPO / "plugins" / "governance-enforcer" / "__init__.py")
    old = prev_module()
    new = load(newpath)

    print(f"pre-fix revision : {PRE_FIX_REV}")
    print(f"module under test: {_red(newpath)}")
    print()

    # ── 1. the reported rate, regex level, on the pre-fix pattern ──────────
    rng = random.Random(20261017)
    hit = 0
    for _ in range(REGEX_SAMPLES):
        if old._PII_PHONE_RE.search(str(uuid.UUID(int=rng.getrandbits(128), version=4))):
            hit += 1
    print("# 1. pre-fix phone pattern vs canonical UUIDs")
    print(f"v4 UUIDs sampled          : {REGEX_SAMPLES}")
    print(f"matched as a phone        : {hit} ({100.0 * hit / REGEX_SAMPLES:.2f}%)")
    print()

    # ── 2. the defect and the fix, gate level, same inputs both revisions ──
    # UUIDs the PRE-FIX gate refuses, found deterministically (no literals).
    samples = [str(uuid.UUID(int=rng.getrandbits(128), version=4)) for _ in range(SAMPLES)]
    old_refused = [u for u in samples if gate(old, f"session {u} ran the check")]
    new_refused = [u for u in samples if gate(new, f"session {u} ran the check")]
    print("# 2. gate verdicts over the same UUID inputs")
    print(f"UUIDs sampled             : {SAMPLES}")
    print(f"refused by pre-fix module : {len(old_refused)}"
          f"  (sha256 handles of the first two: {_handles(old_refused[:2])})")
    print(f"refused by module under test: {len(new_refused)}")
    print()

    # ── 3. coverage is not silently dropped ───────────────────────────────
    dash = "-"
    phones = [
        "call " + "010" + dash + "1234" + dash + "5678",
        "ring +" + "82" + " " + "10" + dash + "1234" + dash + "5678",
    ]
    non_uuid_dashed = "acct " + "1234" + dash + "5678" + dash + "9012"
    print("# 3. real phone formats and the non-UUID dashed run (must fire in BOTH)")
    for label, p in (("national phone", phones[0]),
                     ("+CC grouped phone", phones[1]),
                     ("non-UUID dashed digit run", non_uuid_dashed)):
        print(f"  {label:28s} pre-fix={gate(old, p)!s:5s} under-test={gate(new, p)}")
    print()

    # ── 4. the test file, run through a pytest-capable interpreter ─────────
    proc = subprocess.run(
        ["bash", str(REPO / "ops" / "scripts" / "lib" / "python-with-module.sh"),
         "pytest", "-m", "pytest", str(TARGET_TEST), "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=str(REPO), capture_output=True, text=True, timeout=900,
    )
    summary = [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    summary = re.sub(r"in \d+\.\d+s", "in <t>", summary[-1]) if summary else "(no output)"
    print("# 4. target test file")
    print(f"rc={proc.returncode}")
    print(summary)
    print()

    ok = (len(old_refused) > 0 and len(new_refused) == 0
          and all(gate(old, p) and gate(new, p) for p in phones + [non_uuid_dashed])
          and proc.returncode == 0)
    print(f"**Verdict: {'PASS' if ok else 'FAIL'}**")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
