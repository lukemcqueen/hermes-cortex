#!/usr/bin/env python3
"""PII-gate redaction evidence — adversarial finding ADV-10571-1.

Runnable proof of two claims about ``tests/test_enforcer_pii_gate.py``:

1. it carries no literal personal identifier, and
2. the guard it now ships DISCRIMINATES — the same component scan FAILS on the
   revision before the redaction commit and PASSES on it.

Exit 0 = both claims hold. Exit 1 = one is false; do not ship.

Usage:
    bash ops/scripts/manage/run-pii-gate-evidence.sh            # write + print
    python3 ops/scripts/manage/pii-gate-evidence.py --check     # compare only

The artifact is a committed PUBLIC file, so it must never restate the
identifiers it reports: hits are printed as sha256 handles, and the component
list itself is assembled at runtime so this generator does not carry the
literals either.

Registration policy: this is a REPO-LOCAL evidence generator and is
deliberately NOT registered in cortex-update.sh's register() map, matching its
sibling ops/scripts/manage/task-queue-evidence.py. It reads git history with
``git show <sha>:<path>`` and resolves the repo root from its own location, so
a deployed copy under ~/.hermes-cortex/scripts/ would resolve the wrong root
and fail. No runtime path consumes it.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TARGET = "tests/test_enforcer_pii_gate.py"
ARTIFACT = REPO / "docs" / "evidence" / "pii-gate-redaction-evidence.txt"

# The redaction commit and the one immediately before it (which still carried
# the identifiers, hand-typed and merely split across concatenation).
FIX_COMMIT = "87b6991e"
PRE_FIX_COMMIT = "fd190e42"

# Components of the deny-listed identifiers, assembled at RUNTIME so this file
# does not match its own scan.
COMPONENTS = ("qu" + "een", "real" + "gospel")

_ELAPSED_RE = re.compile(r"\s+in \d+\.\d+s")


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _scan(text: str) -> list[str]:
    low = text.lower()
    return [c for c in COMPONENTS if c in low]


def _handles(names: list[str]) -> str:
    if not names:
        return "-"
    return ",".join(sorted(hashlib.sha256(n.encode()).hexdigest()[:8] for n in names))


def _pytest_summary() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TARGET, "-q"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    summary = lines[-1] if lines else "(no output)"
    return proc.returncode, _ELAPSED_RE.sub("", summary)


def build() -> tuple[str, bool]:
    """Return (artifact text, all_claims_hold)."""
    pre_src = _git("show", f"{PRE_FIX_COMMIT}:{TARGET}")
    fixed_src = (REPO / TARGET).read_text(encoding="utf-8")

    pre_hits = _scan(pre_src)
    fixed_hits = _scan(fixed_src)
    rc, summary = _pytest_summary()

    discriminates = len(pre_hits) > 0
    clean = len(fixed_hits) == 0
    passing = rc == 0
    ok = discriminates and clean and passing

    rows = [
        ("The guard DISCRIMINATES - the pre-fix revision trips it",
         "PASS" if discriminates else "FAIL",
         f"{PRE_FIX_COMMIT}: {len(pre_hits)} component(s) present"
         f" (sha256 handles {_handles(pre_hits)})"),
        ("The redacted revision carries no identifier component",
         "PASS" if clean else "FAIL",
         f"{FIX_COMMIT}: {len(fixed_hits)} component(s)"),
        ("tests/test_enforcer_pii_gate.py passes on the redacted revision",
         "PASS" if passing else "FAIL",
         summary),
    ]

    body = "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows)
    text = (
        "# PII-gate redaction - acceptance evidence (ADV-10571-1)\n"
        "\n"
        "Regenerate with: `bash ops/scripts/manage/run-pii-gate-evidence.sh`\n"
        "\n"
        "Every value below is RE-DERIVED from the repo by running that script.\n"
        "`tests/test_pii_gate_evidence.py` re-runs the generator and compares its\n"
        "output to this committed file, so a hand-written table cannot pass for\n"
        "script output. Identifier hits are printed as sha256 handles - this is a\n"
        "public file and must not restate the identifiers it reports.\n"
        "\n"
        "| Check | Result | Detail |\n"
        "|---|---|---|\n"
        f"{body}\n"
        "\n"
        f"**Verdict: {'PASS' if ok else 'FAIL'}**\n"
    )
    return text, ok


def main() -> int:
    ap = argparse.ArgumentParser(description="PII-gate redaction evidence")
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed artifact, do not write")
    args = ap.parse_args()

    text, ok = build()

    if args.check:
        if not ARTIFACT.exists():
            print(f"MISSING artifact: {ARTIFACT}")
            return 1
        committed = ARTIFACT.read_text(encoding="utf-8")
        if committed != text:
            print("STALE artifact - regenerate: "
                  "bash ops/scripts/manage/run-pii-gate-evidence.sh")
            for a, b in zip(committed.splitlines(), text.splitlines()):
                if a != b:
                    print(f"  committed: {a}\n  derived:   {b}")
            return 1
        if not ok:
            print("artifact matches, but the claim it records does NOT hold")
            return 1
        print("artifact matches the live derivation")
        return 0

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
