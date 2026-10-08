#!/usr/bin/env python3
"""Runnable re-verification for the enterprise-regrets independent-check evidence.

A later reviewer executes this to reproduce every claim in
docs/evidence/enterprise-regrets-independent-check-2026-10-08.txt.
Runs standalone (python3 tests/test_enterprise_regrets_independent_check.py)
or under pytest. Exits non-zero if any check fails.
"""
import base64
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills/software-development/enterprise-regrets/SKILL.md"
CORPUS = REPO / "skills/software-development/enterprise-regrets/references/research-corpus.md"
AV = REPO / "ops/scripts/quality/adversarial-verify.py"
DETECTOR = REPO / "ops/scripts/secret-leak-detector.sh"
RELATED = [
    "code-review", "architecture-review", "engineering-approach",
    "data-structure-efficiency-review", "root-cause-debugging",
]
# Digest of the hyphenated family-relation phrase (it is itself PII
# deny-listed and must never be spelled out in shared-surface files).
PHRASE_DIGEST = base64.b64decode("39FK/mZ2ftxwx3jPIwib6pGRDJGtG7qyGfqdtWUYY+s=")

failures = []


def check(label, ok, detail=""):
    label = str(label) if label is not None else "<unlabelled>"
    detail = "" if detail is None else str(detail)
    print(f"[{'PASS' if ok else 'FAIL'}] {label} {detail}")
    if not ok:
        failures.append(label)


def run_gate(path):
    r = subprocess.run(
        [sys.executable, str(AV), "--file", str(path), "--level", "A2", "--gate"],
        capture_output=True, text=True, cwd=REPO,
    )
    return r.returncode, (r.stdout + r.stderr)


def run_all_checks():
    rc1, out1 = run_gate(SKILL)
    check("adversarial gate SKILL.md", rc1 == 0 and "GATE_PASSED" in out1, f"rc={rc1}")

    rc2, out2 = run_gate(CORPUS)
    check("adversarial gate research-corpus.md", rc2 == 0 and "GATE_PASSED" in out2, f"rc={rc2}")

    # Frontmatter (full YAML parse via yaml.safe_load)
    try:
        import yaml
        text = SKILL.read_text()
        check("SKILL.md starts with '---'", text.startswith("---"))
        fm = yaml.safe_load(text[3:text.find("\n---", 3)])
        check("frontmatter name", fm.get("name") == "enterprise-regrets")
        desc = fm.get("description", "")
        check("description <= 60 chars", len(desc) <= 60, f"len={len(desc)}")
        check("description ends with '.'", desc.endswith("."))
        check("platforms present", bool(fm.get("platforms")))
    except ImportError:
        check("yaml module available", False, "pip install pyyaml to run this check")

    for name in RELATED:
        p = REPO / "skills/software-development" / name / "SKILL.md"
        check(f"related_skill {name} resolves", p.is_file(), str(p))

    rc = subprocess.run(["bash", str(DETECTOR), str(SKILL), str(CORPUS)],
                        capture_output=True, text=True, cwd=REPO)
    check("secret-leak-detector.sh", rc.returncode == 0 and not rc.stdout.strip(),
          f"rc={rc.returncode}")

    for path in (SKILL, CORPUS):
        t = path.read_text()
        check(f"no 8-digit runs ({path.name})", not re.search(r"\b\d{8}\b", t))
        # Scan for the deny-listed family-relation phrase via digest, not literal.
        low = t.lower()
        hit = any(
            hashlib.sha256(low[i:i + 10].encode()).digest() == PHRASE_DIGEST
            for i in range(len(low) - 9)
            if low[i].isalnum()
        )
        check(f"no deny-listed family-relation phrase ({path.name})", not hit)
        check(f"no at-sign ({path.name})", "@" not in t)
        check(f"no machine-local /home/<user>/ paths ({path.name})",
              not re.search(r"/home/\w+/", t))

    check("SKILL.md byte count 15926", len(SKILL.read_bytes()) == 15926,
          str(len(SKILL.read_bytes())))
    check("SKILL.md line count 203", len(SKILL.read_text().splitlines()) == 203)
    check("corpus byte count 12559", len(CORPUS.read_bytes()) == 12559,
          str(len(CORPUS.read_bytes())))
    check("corpus line count 78", len(CORPUS.read_text().splitlines()) == 78)

    print("\nALL CHECKS PASSED" if not failures
          else f"\n{len(failures)} CHECK(S) FAILED")
    return 1 if failures else 0


def test_all_checks_pass():
    """pytest entry: the full independent-check battery must pass."""
    failures.clear()
    assert run_all_checks() == 0


if __name__ == "__main__":
    sys.exit(run_all_checks())