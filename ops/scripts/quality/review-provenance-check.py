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
# A file can legitimately present a model-ish header without being a review at all (a design doc
# whose header names the model it is about — measured on docs/older/plans/…decision-model.md). The
# gate must let that be declared TRUTHFULLY, or its only remedy is a false statement:
NOT_A_REVIEW = "provenance: not-a-review"
DECLARATIONS = (ADVISORY, NOT_A_REVIEW)
RECORDED_RE = re.compile(r"recorded-in:\s*adversarial_reviews\s+review_id=([A-Za-z0-9._-]+)",
                         re.IGNORECASE)
HEADER_LINES = 10          # the declaration belongs at the TOP; a buried one is not a declaration

# DETECTION — four candidate discriminators were measured against the live tree, and three were
# wrong. Recording the failures is the point: each was plausible and each was refuted by data.
#   * filename alone (`*review*`) flagged evidence notes whose names merely contained "review";
#   * phrases ("adversarial review", "independent review") fired on 8 briefings that DISCUSS reviews;
#   * a `model:` line searched through 40 lines flagged a design PLAN whose line 38 read "model: a
#     395M ModernBERT encoder" (docs/older/plans/…decision-model.md);
#   * a `reviews/` PATH rule flagged 10 files under docs/reviews/ — soul-refinement mining outputs,
#     including a `.py` and a `.json`, none of them a model review.
# What survives is the union of STRUCTURAL facts on a 10-line header, over every text file under
# docs/ in any extension, so renaming, changing extension or moving directory does not evade it:
#   1. a header CLAIM (`recorded-in: adversarial_reviews review_id=…`) — verified against the store;
#   2. the repo's own review-write-up convention (`pro-review*`);
#   3. a `model:` line in the header — a model review names its model up front.
# The honest limits, stated rather than papered over (a plan review by the governed reviewer asked
# for exactly this instead of a promise of coverage):
#   * a review written into an innocently-named file that names no model is indistinguishable from
#     commentary by these rules — commentary is not evidence, and the push receipt comes from
#     `end_change`'s reviewer, never from a file;
#   * a declaration can be a LIE: nothing verifies that a file declaring `advisory` is not really a
#     review. What the gate guarantees is the other direction — nothing can CLAIM a recorded review
#     without a row to back it, and the row's recorder is printed so a reader can judge it;
#   * a row PROVES a review exists in the sink, not that it was independent: the same agent can run
#     `--review` on its own cycle. That is why the OK line names the reviewer_id and model;
#   * a review delivered as a URL, or quoted into a cycle note / commit message / chat, is not a
#     file here and is not covered at all.
MODEL_LINE_RE = re.compile(r"^\s*>?\s*model:\s*\S+", re.IGNORECASE | re.MULTILINE)


def _presents_a_review(path: Path, header: str) -> bool:
    if path.name.lower().startswith("pro-review"):
        return True
    return bool(MODEL_LINE_RE.search(header))


def review_artifacts(docs_dir: Path) -> list[Path]:
    """Every text artifact under docs/ — any directory, any extension. The CLAIM decides, not the name.

    Narrowing this to `docs/evidence/*.md` was a loophole two ways: a review written into a `.txt`
    (the repo's own transcripts are .txt) or into `docs/reviews/` or the repo root would never be
    read at all, which is a one-move evasion of the whole gate. Reading a 10-line header per file is
    cheap; the scope belongs on the tree, not on a name pattern.
    """
    if not docs_dir.is_dir():
        return []
    out = []
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gz", ".zip"}:
            continue                                   # not text; nothing to declare
        out.append(path)
    return out


def _header(path: Path) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()
                         [:HEADER_LINES])
    except OSError:
        return ""


def _recorded_ids(db_path: Path) -> dict[str, tuple[str, str]] | None:
    """review_id → (reviewer_id, model) for rows in the store, or None when it cannot be read."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            rows = conn.execute("SELECT review_id, reviewer_id, reviewer_model "
                                "FROM adversarial_reviews").fetchall()
            return {str(r[0]): (str(r[1] or "?"), str(r[2] or "?")) for r in rows}
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def check(repo: Path, db_path: Path) -> int:
    docs = repo / "docs"
    artifacts = review_artifacts(docs)
    if not artifacts:
        print(f"nothing to check: no text artifacts under {docs}")
        return 0

    violations, unverifiable, checked, presenting, ignored = [], [], 0, 0, 0
    cached_ids: dict[str, tuple[str, str]] | None | bool = False   # False = not loaded yet
    for path in artifacts:
        rel = path.relative_to(repo)
        header = _header(path)
        declared_recorded = RECORDED_RE.search(header)
        if declared_recorded:
            # A CLAIM is checked wherever it appears — filename, directory and extension are
            # irrelevant to whether the row it names actually exists.
            checked += 1
            if cached_ids is False:
                cached_ids = _recorded_ids(db_path)
            if cached_ids is None:
                unverifiable.append(f"{rel} claims review_id={declared_recorded.group(1)} but the "
                                    f"store at {db_path} could not be read")
                continue
            rid = declared_recorded.group(1)
            if rid not in cached_ids:
                violations.append(f"{rel}: claims review_id={rid}, which is NOT in "
                                  f"adversarial_reviews — a review that was never recorded")
                continue
            # Name the row's recorder: a row PROVES a review exists in the sink, not that anyone
            # independent wrote it (the same agent can run --review on its own cycle), so the
            # reader gets the reviewer identity to judge, instead of a bare OK.
            who, model = cached_ids[rid]
            print(f"OK    {rel} (recorded review_id={rid}; reviewer={who}; model={model})")
            continue
        if not _presents_a_review(path, header):
            ignored += 1
            continue
        presenting += 1
        declared = next((d for d in DECLARATIONS if d in header.lower()), None)
        if declared:
            print(f"OK    {rel} (declared '{declared}' — commentary, never citable as verification)")
            continue
        violations.append(f"{rel}: presents a review with no provenance — declare one of "
                          f"{' or '.join(repr(d) for d in DECLARATIONS)} or "
                          f"'recorded-in: adversarial_reviews review_id=<id>' "
                          f"in the first {HEADER_LINES} lines")

    print(f"\nartifacts presenting a review: {presenting} of {len(artifacts)} text file(s) under "
          f"docs/ ({ignored} ignored, {checked} recorded claim(s) checked)")
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
