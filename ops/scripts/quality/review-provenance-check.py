#!/usr/bin/env python3
"""review-provenance-check.py — a review artifact must DECLARE where it came from.

Why this exists. An agent can call a model from anywhere — a scratch script, a one-liner — and
then write the reply up as a review. Nothing about that is auditable: the enforcer audits TOOL
CALLS, and an HTTP request from a subprocess is not one. The operator's objection was exact: if one
agent can produce review-looking evidence outside the governed path, every agent can, and the payoff
for doing it badly is manufactured proof of verification.

The governed path already exists and records itself:
  * the CLOSE-TIME reviewer, whose verdict mints the push receipt (`end_change`);
  * `ops/scripts/orch-bus/adversarial-review.py --cycle-id N --review`, which writes a row to
    `adversarial_reviews` in the loop-governance store.
So the enforceable rule is about the ARTIFACT, not about which executable ran: a committed file
under docs/evidence/ that presents itself as a review must either

  1. point at a RECORDED review — `recorded-in: adversarial_reviews review_id=<id>` — and that row
     must actually exist (a claim with no row is fabrication), or
  2. declare plainly that it is NOT evidence — `provenance: advisory` — in which case it is read as
     commentary and can never be cited as verification.

One line, in the header, either true or absent. Undeclared review artifacts fail. This is what stops
a shadow review from being mistaken for the sanctioned one; it does not pretend to stop an agent
from calling a model, which no file-level rule could honestly promise.

Exit codes: 0 clean, 1 at least one violation (named), 3 could not verify (no evidence tree, or a
recorded-in claim that cannot be checked because the store is unreadable — never a silent pass).
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"
ADVISORY = "provenance: advisory"
RECORDED_RE = re.compile(r"recorded-in:\s*adversarial_reviews\s+review_id=([A-Za-z0-9._-]+)",
                         re.IGNORECASE)
HEADER_LINES = 40          # the declaration is part of the artifact's header, not its small print

# What counts as "presenting a review". Two earlier discriminators were measured against the LIVE
# tree and both were wrong, which is why this one is narrow:
#   * FILENAME (`*review*`) flagged evidence notes that merely had the word in their name
#     (`orch-skill-lifecycle-cycle-11708-close-review.md`) — and would have missed a review in an
#     innocently-named file;
#   * PHRASES ("adversarial review", "independent review", …) fired on 8 briefings and cycle notes
#     that DISCUSS reviews without being one (`reflexion-check-*.md`, `cycle-2938-evidence.md`).
# A gate that fires on the healthy majority teaches its reader to ignore it. What a model review
# actually carries is the MODEL — so that is the discriminator, plus this repo's own filename
# convention for these write-ups.
MODEL_LINE_RE = re.compile(r"^\s*>?\s*model:\s*\S+", re.IGNORECASE | re.MULTILINE)


def _presents_a_review(path: Path, header: str) -> bool:
    return bool(MODEL_LINE_RE.search(header)) or path.name.lower().startswith("pro-review")


def review_artifacts(evidence_dir: Path) -> list[Path]:
    """Every markdown artifact under docs/evidence/ — the CLAIM decides, not the filename.

    Scanning by name (`*review*`) was the first version and it was wrong in BOTH directions: it
    flagged evidence notes that merely had the word in their name, and it would have missed a model
    review written into innocently-named file — a one-word evasion of the whole gate. Reading a
    header per file is cheap; the discriminator belongs on content.
    """
    if not evidence_dir.is_dir():
        return []
    return sorted(p for p in evidence_dir.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".md")


def _header(path: Path) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()
                         [:HEADER_LINES])
    except OSError:
        return ""


def _recorded_ids(db_path: Path) -> set[str] | None:
    """Review ids present in the store, or None when the store cannot be read."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            rows = conn.execute("SELECT review_id FROM adversarial_reviews").fetchall()
            return {str(r[0]) for r in rows}
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def check(repo: Path, db_path: Path) -> int:
    evidence = repo / "docs" / "evidence"
    artifacts = review_artifacts(evidence)
    presenting = [p for p in artifacts if _presents_a_review(p, _header(p))]
    if not presenting:
        print(f"nothing to check: {len(artifacts)} evidence file(s) under {evidence} present no "
              f"model review (an evidence note is not a review — only a claim is gated)")
        return 0

    violations, unverifiable, checked = [], [], 0
    cached_ids: set[str] | None | bool = False     # False = not loaded yet
    for path in presenting:
        rel = path.relative_to(repo)
        header = _header(path)
        declared_recorded = RECORDED_RE.search(header)
        if declared_recorded:
            checked += 1
            if cached_ids is False:
                cached_ids = _recorded_ids(db_path)
            if cached_ids is None:
                unverifiable.append(f"{rel} claims review_id={declared_recorded.group(1)} but the "
                                    f"store at {db_path} could not be read")
                continue
            if declared_recorded.group(1) not in cached_ids:
                violations.append(f"{rel}: claims review_id={declared_recorded.group(1)}, which is "
                                  f"NOT in adversarial_reviews — a review that was never recorded")
                continue
            print(f"OK    {rel} (recorded review_id={declared_recorded.group(1)})")
            continue
        if ADVISORY in header.lower():
            print(f"OK    {rel} (declared advisory — not evidence, never citable as verification)")
            continue
        violations.append(f"{rel}: presents a review with no provenance — add either "
                          f"'{ADVISORY}' or 'recorded-in: adversarial_reviews review_id=<id>'")

    print(f"\nartifacts presenting a review: {len(presenting)} of {len(artifacts)} evidence file(s) "
          f"(recorded claims checked: {checked})")
    if violations:
        print(f"\n❌ {len(violations)} undeclared or unbacked review artifact(s):")
        for v in violations:
            print(f"   {v}")
        return 1
    if unverifiable:
        print(f"\n⚠️  COULD NOT VERIFY {len(unverifiable)} claim(s):")
        for u in unverifiable:
            print(f"   {u}")
        return 3
    print("✅ every review artifact declares its provenance")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=None, help="repo root (default: git toplevel of cwd)")
    p.add_argument("--db", default=str(DEFAULT_DB), help="loop-governance store")
    args = p.parse_args()
    if args.repo:
        repo = Path(args.repo).expanduser()
    else:
        import subprocess
        try:
            repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                                text=True, stderr=subprocess.DEVNULL).strip())
        except Exception:
            print("COULD NOT VERIFY: no --repo and not inside a git tree", file=sys.stderr)
            return 3
    return check(repo, Path(args.db).expanduser())


if __name__ == "__main__":
    sys.exit(main())
