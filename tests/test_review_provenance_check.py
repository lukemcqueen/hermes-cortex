"""Enforcement: a review artifact must declare provenance, and a RECORDED claim must be true.

Operator-directed (2026-10-14), and the reason this is a gate rather than a note: an agent can call
a model from a scratch script and write the reply up as a review. The enforcer audits TOOL CALLS and
an HTTP request from a subprocess is not one, so the enforceable rule is about the ARTIFACT — a
docs/evidence file that presents itself as a review must either point at a row in
`adversarial_reviews` (and that row must EXIST) or declare `provenance: advisory`. Undeclared ones
FAIL the doctor, and a doctor FAIL blocks the push for every agent on the host.

Both directions are proven here, and the third outcome too: a check that cannot read the store must
say COULD NOT VERIFY rather than pass. Every case runs on planted fixtures in a temp tree.
"""
import importlib.util
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "ops" / "scripts" / "quality" / "review-provenance-check.py"

SCHEMA = ("CREATE TABLE adversarial_reviews (review_id TEXT PRIMARY KEY, cycle_id INTEGER,"
          " reviewer_id TEXT, reviewer_model TEXT, verdict TEXT, findings_json TEXT,"
          " summary TEXT, ts TEXT)")


def _load():
    spec = importlib.util.spec_from_file_location("review_provenance_under_test", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tree(tmp: Path, artifacts: dict, reviews: list[str] | None = None) -> tuple[Path, Path]:
    """Plant artifacts. A key starting `docs/` is repo-root-relative; any other key lands in
    docs/evidence/ (the common case, which is why the shorter form is the default)."""
    for name, text in artifacts.items():
        path = (tmp / name) if name.startswith("docs/") else (tmp / "docs" / "evidence" / name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = tmp / "loop-governance.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(SCHEMA)
        for rid in (reviews or []):
            conn.execute("INSERT INTO adversarial_reviews (review_id, cycle_id) VALUES (?,?)",
                         (rid, 1))
        conn.commit()
    finally:
        conn.close()
    return tmp, db


def _run(tmp: Path, db: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECKER), "--repo", str(tmp), "--db", str(db)],
                          capture_output=True, text=True, timeout=120)


def test_an_undeclared_review_artifact_fails():
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"pro-review-thing.md":
                                  "# A review\n\nI asked the model and it said the code was fine.\n"})
        assert _load().check(tmp, db) == 1, "an undeclared review artifact must FAIL — that is the gate"


def test_a_recorded_claim_that_does_not_exist_is_fabrication():
    """The abuse this gate exists for: pointing at a 'recorded' review that was never recorded."""
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"pro-review-claim.md":
                                  "> recorded-in: adversarial_reviews review_id=not-a-real-row\n\n"
                                  "# Independent review\n"})
        proc = _run(tmp, db)
        assert proc.returncode == 1, proc.stdout
        assert "NOT in adversarial_reviews" in proc.stdout, proc.stdout


def test_a_recorded_claim_that_exists_passes():
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"pro-review-real.md":
                                  "> recorded-in: adversarial_reviews review_id=rev-aaaa\n\n# r\n"},
                        reviews=["rev-aaaa"])
        proc = _run(tmp, db)
        assert proc.returncode == 0, proc.stdout
        assert "recorded review_id=rev-aaaa" in proc.stdout


def test_an_advisory_declaration_passes_and_is_not_evidence():
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"pro-review-advisory.md":
                                  "> provenance: advisory\n\n# Supplementary opinion, not evidence\n"})
        proc = _run(tmp, db)
        assert proc.returncode == 0, proc.stdout
        assert "never citable as verification" in proc.stdout, proc.stdout


def test_an_unreadable_store_is_could_not_verify_not_a_pass():
    """A recorded claim we cannot check is the third outcome — never a silent PASS."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "docs" / "evidence").mkdir(parents=True)
        (tmp / "docs" / "evidence" / "pro-review-x.md").write_text(
            "> recorded-in: adversarial_reviews review_id=rev-bbbb\n", encoding="utf-8")
        missing_db = tmp / "nope.db"
        proc = _run(tmp, missing_db)
        assert proc.returncode == 3, proc.stdout
        assert "COULD NOT VERIFY" in proc.stdout, proc.stdout


def test_non_review_artifacts_are_ignored():
    """Scope check: the gate must not demand provenance from documents that are not reviews.

    These are the real files the earlier, wrong discriminators flagged — a close-out EVIDENCE note,
    a task-named file, and the soul-refinement artefacts under docs/reviews/ (including a .py and a
    .json). Reading a 10-line header is cheap; demanding a declaration from all of them is not."""
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {
            "purge-guards-2026-10-14.txt": "a transcript",
            "notes.md": "x",
            "docs/reviews/soul-refinement-2026-10-07.md": "# Soul refinement\n\nSession notes.\n",
            "docs/reviews/user_msgs.json": '{"messages": []}',
            "docs/reviews/extract.py": "print('hi')\n",
            "docs/evidence/orch-skill-lifecycle-cycle-11708-close-review.md":
                "# orch-skill-lifecycle cycle 11708 — evidence notes\n\n## What this run changed\n",
            "docs/evidence/reviewer-tiering-cycle-3877.md":
                "# Reviewer tiering — evidence (cycle 3877)\n\nThis file backs the claims in the note.\n",
        })
        proc = _run(tmp, db)
        assert proc.returncode == 0, proc.stdout
        assert "0\n" not in proc.stdout.split("artifacts presenting")[0]
        assert "artifacts presenting a review: 0" in proc.stdout, proc.stdout


def test_a_model_line_buried_deep_does_not_flag_a_design_document():
    """Measured case: docs/older/plans/…-decision-model.md has 'model:' at line 38 and is a PLAN.
    The header window is 10 lines precisely so a design document is not read as a review."""
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"plan.md":
                                  "# Plan\n\n" + "\n".join(f"line {i}" for i in range(30))
                                  + "\nmodel: a 395M ModernBERT encoder\n"})
        proc = _run(tmp, db)
        assert proc.returncode == 0, proc.stdout
        assert "artifacts presenting a review: 0" in proc.stdout


def test_an_artifact_that_names_a_model_is_gated_even_if_the_filename_is_innocent():
    """The discriminator is the CLAIM, not the name: this is what closes the filename loophole."""
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"notes-about-the-change.md":
                                  "# Thoughts\n\nmodel: some-heavy-model\n\nIt said the code was "
                                  "fine, so I pushed.\n"})
        proc = _run(tmp, db)
        assert proc.returncode == 1, proc.stdout
        assert "no provenance" in proc.stdout


def test_the_real_repo_declares_provenance_today():
    """The repo's own artifacts must pass their own gate — otherwise the gate is aspirational."""
    proc = subprocess.run([sys.executable, str(CHECKER), "--repo", str(REPO)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout}"


def test_a_design_doc_naming_a_model_can_declare_itself_not_a_review():
    """The plan review's finding 3: the `model:` trigger is weak, so a design doc about a model can
    trip it. The remedy must be a TRUTHFUL statement, not a false one — hence a second declaration."""
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"docs/plans/encoder-choice.md":
                                  "# Encoder choice\n\nmodel: a 395M ModernBERT encoder\n\n"
                                  "provenance: not-a-review\n"})
        proc = _run(tmp, db)
        assert proc.returncode == 0, proc.stdout
        assert "not-a-review" in proc.stdout, proc.stdout


def test_the_ok_line_names_who_recorded_a_claimed_review():
    """The plan review's finding 4: a row proves a review EXISTS, not that it was independent —
    the same agent can run --review on its own cycle. So the reader gets the recorder's identity."""
    with tempfile.TemporaryDirectory() as t:
        tmp, db = _tree(Path(t), {"pro-review-x.md":
                                  "> recorded-in: adversarial_reviews review_id=rev-cccc\n"},
                        reviews=["rev-cccc"])
        proc = _run(tmp, db)
        assert proc.returncode == 0, proc.stdout
        assert "reviewer=" in proc.stdout and "model=" in proc.stdout, proc.stdout


def test_the_declaration_can_lie_and_that_is_documented_not_hidden():
    """The residual the plan review pressed on: a file can declare 'advisory' and lie. The gate
    cannot detect that, and the source says so instead of implying coverage it does not have."""
    src = CHECKER.read_text(encoding="utf-8")
    assert "a declaration can be a LIE" in src
    assert "does not verify" not in src.lower() or "can be a LIE" in src
