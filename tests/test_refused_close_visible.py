#!/usr/bin/env python3
"""A refused close is visible at the moment work is stacked under it.

Luke (2026-10-02): "will your lock issue be a continual issue?" and then "fix this".

The fault this fixes: a refused close leaves the lock HELD with nothing saying so.
The next change then gets stacked under it in silence, and the reviewer later reads
a task description that no longer matches the diff — the one case the close-out skill
calls unclosable by a worker. That is what happened to cycle 10445, and the same
door is open for every agent.

Two halves, both asserted here:

  A. The GATE records the refusal on the lock (`close_refused`: cycle, verdict,
     blocking count, finding ids) when the review returns MEDIUM+ findings, and
     clears the marker when the review is CLEAN. A worker cannot forge the marker —
     only the gate writes it.
  B. The pre-commit ADVISORY fires exactly when a matching lock carries that marker,
     and stays silent otherwise. It always exits 0: it warns, it never blocks. (A
     blocking version could deadlock an agent whose close is legitimately stuck,
     which is a worse failure than the one it prevents.)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_refused", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

# Tests must NOT write into the PRODUCTION governance log: the gate's logger appends
# to ~/.hermes-cortex/logs/loop-governance.log, so running these tests injected
# fabricated "cycle 1" / "cycle 999" lines into the audit trail (found 2026-10-02 by
# reading the log back). The audit log must only ever contain real cycles, so the
# gate logger is silenced here and the refused-close test asserts the file does not
# grow during a run.
import logging as _logging  # noqa: E402

_gate_log = _logging.getLogger("loop-governance")
# Level alone is the silencing — the gate's FileHandler stays ATTACHED on purpose:
# test_tests_do_not_pollute_the_production_log re-enables the level to prove the
# handler really targets the real production log (a control that clearing handlers
# here would make impossible).
_gate_log.setLevel(_logging.CRITICAL + 1)
_gate_log.propagate = False

ADVISORY = REPO / "ops" / "scripts" / "governance-refused-close-advisory.sh"
SLUG = "hermes-cortex"
_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


FINDINGS_JSON = json.dumps({
    "verdict": "FINDINGS",
    "findings": [{
        "finding_id": "ADV-999-1", "severity": "high", "technique": "unverified-claim",
        # NB: the evidence must QUOTE text that is really in the material, or Layer 1
        # refutation correctly drops the finding and nothing blocks (that is the
        # refutation layer doing its job, not a bug — learned the first run).
        "target": "note", "evidence": "a note", "recommendation": "commit a test",
    }],
})
CLEAN_JSON = json.dumps({"verdict": "CLEAN", "findings": []})


def _make_repo(home: Path) -> Path:
    """A governed repo under a temp HOME, with a COMPLEX uncommitted change."""
    repo = home / SLUG
    (repo / "mcp-servers").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("base\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    # an always-review path + >50 lines, left uncommitted (uncommitted work counts)
    (repo / "mcp-servers" / "big.py").write_text("\n".join(f"x{i} = {i}" for i in range(60)) + "\n")
    # the reviewer prompt template must be present or the gate refuses before it
    # ever reviews (that refusal is itself now marked — see TEMPLATE_MISSING).
    tmpl = repo / getattr(mcp, "REVIEW_TEMPLATE_REL", "docs/templates/adversarial-reviewer-prompt.md")
    tmpl.parent.mkdir(parents=True, exist_ok=True)
    tmpl.write_text("You are an independent adversarial reviewer.\n\n"
                    + mcp.REVIEW_MARKER + "\n")
    return repo


def _block_text(block) -> str:
    """The refusal message — names WHICH path refused, so a failure is diagnosable."""
    try:
        return block.content[0].text
    except Exception:
        return str(block)


def test_refused_close_visible() -> None:
    # ── B. the advisory script (real subprocess, no mocks) ──
    print("B. the pre-commit advisory fires on a refused-close lock, and only then")
    with tempfile.TemporaryDirectory() as td:
        state = Path(td)
        lock = state / ".governance-test.json"

        # B1: no lock at all
        out = subprocess.run(["bash", str(ADVISORY), SLUG],
                             capture_output=True, text=True,
                             env={**os.environ, "GOVERNANCE_STATE_DIR": str(state)})
        _check("silent with no lock", "ADVISORY" not in out.stdout and out.returncode == 0)

        # B2: lock for this repo WITHOUT the marker
        lock.write_text(json.dumps({"repo_slug": SLUG, "task_id": "t"}))
        out = subprocess.run(["bash", str(ADVISORY), SLUG], capture_output=True, text=True,
                             env={**os.environ, "GOVERNANCE_STATE_DIR": str(state)})
        _check("silent without the marker", "ADVISORY" not in out.stdout and out.returncode == 0)

        # B3: lock for a DIFFERENT repo, carrying the marker → silent here
        lock.write_text(json.dumps({"repo_slug": "other-repo", "close_refused": {"cycle_id": 5}}))
        out = subprocess.run(["bash", str(ADVISORY), SLUG], capture_output=True, text=True,
                             env={**os.environ, "GOVERNANCE_STATE_DIR": str(state)})
        _check("silent for another repo's lock", "ADVISORY" not in out.stdout)

        # B4: this repo's lock WITH the marker → the advisory, naming the cycle
        lock.write_text(json.dumps({
            "repo_slug": SLUG, "task_id": "t",
            "close_refused": {"at": "2026-10-02T05:43:21Z", "cycle_id": 10445,
                              "verdict": "FINDINGS", "blocking": 4,
                              "finding_ids": ["ADV-10445-1", "ADV-10445-2"]}}))
        out = subprocess.run(["bash", str(ADVISORY), SLUG], capture_output=True, text=True,
                             env={**os.environ, "GOVERNANCE_STATE_DIR": str(state)})
        _check("warns on a refused close", "ADVISORY" in out.stdout, out.stdout[:200])
        _check("names the refused cycle", "10445" in out.stdout)
        _check("names the blocking findings", "ADV-10445-1" in out.stdout)
        _check("offers rereview_change as the exit", "rereview_change" in out.stdout)
        _check("never blocks (exit 0)", out.returncode == 0, f"rc={out.returncode}")

    # ── A. the gate records and clears the marker (real gate code path) ──
    print("A. the gate marks the lock on a refusal and clears it on CLEAN")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        repo = _make_repo(home)
        setattr(mcp, "HOME", home)

        lock_state: dict = {"repo_slug": SLUG, "task_id": "refused-close-visible",
                            "session_id": "sess-test", "description": "test change"}
        writes: list[dict] = []
        setattr(mcp, "_read_lock", lambda args=None: dict(lock_state))
        setattr(mcp, "_write_lock", lambda st, args=None: writes.append(dict(st)))
        setattr(mcp, "_record_review", lambda *a, **k: None)  # covered elsewhere
        # Layers 1 & 2 (deterministic refutation + fast-model triage) have their own
        # suites, and Layer 2 would call the LIVE judge configured in the cortex env —
        # which can legitimately lower a synthetic finding. Neutralise both here so
        # this test isolates the WIRING: a MEDIUM+ verdict must reach the refusal path
        # and mark the lock.
        setattr(mcp, "_refute_findings", lambda findings, material: [])
        setattr(mcp, "_triage_findings", lambda findings, material, **k: findings)

        lock = {"repo_slug": SLUG, "task_id": "refused-close-visible", "session_id": "sess-test",
                "description": "test change",
                "started_at": datetime.now(timezone.utc).isoformat()}
        cycle = {"id": 999, "outcome_note": "a note"}

        setattr(mcp, "_call_reviewer", lambda prompt, author=None: FINDINGS_JSON)
        block = mcp._adversarial_review_gate(lock, cycle)
        _check("a FINDINGS review blocks the close", block is not None)
        marker = (writes[-1] if writes else {}).get("close_refused")
        _check("the lock records close_refused", bool(marker),
               f"writes={writes} block={_block_text(block)[:160] if block else ''}")
        if marker:
            _check("marker names the cycle", marker.get("cycle_id") == 999, str(marker))
            _check("marker names the verdict", str(marker.get("verdict")).upper() == "FINDINGS")
            _check("marker counts blocking findings", marker.get("blocking") == 1, str(marker))
            _check("marker carries the finding ids", "ADV-999-1" in (marker.get("finding_ids") or []))

        writes.clear()
        # pre-seed the marker so CLEARING is genuinely exercised (clearing with no
        # marker correctly writes nothing — that is not a test of anything).
        lock_state["close_refused"] = {"at": "x", "cycle_id": 999, "verdict": "FINDINGS"}
        setattr(mcp, "_call_reviewer", lambda prompt, author=None: CLEAN_JSON)
        block2 = mcp._adversarial_review_gate(lock, cycle, force=True)
        _check("a CLEAN review does not block", block2 is None)
        _check("the marker is CLEARED on CLEAN",
               bool(writes) and "close_refused" not in writes[-1], f"writes={writes}")

        # A refused close is a refused close: an UNREACHABLE reviewer holds the lock
        # exactly like a MEDIUM+ verdict, so it must be visible too (this path had no
        # marker until this test found it).
        writes.clear()

        def _unreachable(prompt, author=None):
            raise RuntimeError("reviewer unreachable (test)")

        setattr(mcp, "_call_reviewer", _unreachable)
        block3 = mcp._adversarial_review_gate(lock, cycle, force=True)
        _check("an unreachable reviewer refuses the close", block3 is not None)
        m3 = (writes[-1] if writes else {}).get("close_refused")
        _check("the outage is recorded on the lock too",
               bool(m3) and str(m3.get("verdict")) == "REVIEWER_UNAVAILABLE", f"marker={m3}")

    assert not _F, f"{len(_F)} refused-close check(s) failed: {', '.join(_F)}"


def test_tests_do_not_pollute_the_production_log() -> None:
    """Running the gate under test must not append to the governance audit log.

    Premise, checked rather than assumed (adversarial finding ADV-10463-1 asked this
    point directly): loop-gov-mcp.py builds its RotatingFileHandler AT IMPORT TIME
    over (CORTEX_DEPLOY_HOME or Path.home()/".hermes-cortex")/logs/loop-governance.log.
    Patching mcp.HOME afterwards redirects where the gate looks for the REPO, not where
    it logs — so the production log is the correct file to assert on.

    But a premise is not a test. DIRECTION 1 proves the handler really does reach the
    production log: with the logger's level restored, the gate writes to it even while
    mcp.HOME is patched to a temp dir. Only then does DIRECTION 2 mean anything: with
    the silencing on, the same run appends nothing. If the reviewer's concern were
    true, DIRECTION 1 would fail and this test would fail with it.
    """
    log_path = (Path(os.environ.get("CORTEX_DEPLOY_HOME") or (Path.home() / ".hermes-cortex"))
                / "logs" / "loop-governance.log")

    def _run_gate() -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _make_repo(home)
            setattr(mcp, "HOME", home)      # repo lookup only — see docstring
            lock_state: dict = {"repo_slug": SLUG, "task_id": "t", "session_id": "s"}
            setattr(mcp, "_read_lock", lambda args=None: dict(lock_state))
            setattr(mcp, "_write_lock", lambda st, args=None: None)
            setattr(mcp, "_record_review", lambda *a, **k: None)
            setattr(mcp, "_refute_findings", lambda findings, material: [])
            setattr(mcp, "_triage_findings", lambda findings, material, **k: findings)
            setattr(mcp, "_call_reviewer", lambda prompt, author=None: FINDINGS_JSON)
            lock = {"repo_slug": SLUG, "task_id": "t", "session_id": "s", "description": "d",
                    "started_at": datetime.now(timezone.utc).isoformat()}
            mcp._adversarial_review_gate(lock, {"id": 999, "outcome_note": "a note"})

    # DIRECTION 1 — control, and it writes NOTHING (writing to prove a file is not
    # written to would be self-defeating):
    #   (a) the gate's logger really has a handler BOUND to the production log;
    #   (b) with the level restored, this code path really does emit records.
    # Together they prove DIRECTION 2 is not vacuous. If patching mcp.HOME redirected
    # the gate's logging, (a) would fail — that is ADV-10463-1's concern, settled by
    # measurement rather than by argument.
    file_handler = None
    for h in list(_gate_log.handlers):
        base = getattr(h, "baseFilename", "")
        if base and Path(base).resolve() == log_path.resolve():
            file_handler = h
            break
    assert file_handler is not None, (
        f"CONTROL FAILED: no handler on the gate logger is bound to {log_path} "
        f"(handlers={[getattr(h, 'baseFilename', str(h)) for h in _gate_log.handlers]}) — "
        "then an assertion that the file does not grow while silenced would be vacuous"
    )

    seen: list[str] = []

    class _Counter(_logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    _gate_log.removeHandler(file_handler)          # detach so the control writes no file
    counter = _Counter()
    _gate_log.addHandler(counter)
    _gate_log.setLevel(_logging.DEBUG)
    try:
        _run_gate()
    finally:
        _gate_log.removeHandler(counter)
        _gate_log.addHandler(file_handler)         # re-attach for DIRECTION 2
        _gate_log.setLevel(_logging.CRITICAL + 1)
    assert seen, ("CONTROL FAILED: the gate emitted no records even unsilenced, so there "
                  "is nothing for the silencing to suppress")
    print(f"  PASS  control: handler bound to the real log; {len(seen)} record(s) emitted "
          f"when unsilenced (none written to the file)")

    # DIRECTION 2 — the guarantee: silenced, the same run injects NO fabricated cycle.
    #
    # Measured by CONTENT, not by byte size. A size-equality assertion is racy: another
    # process (a cron, a deploy, another agent) may legitimately append to the audit trail
    # during this window, and on 2026-10-02 that turned a concurrent write into a failure
    # of THIS test — a false report about the thing it claims to measure. What matters is
    # that no FABRICATED cycle (the ids/strings these tests use) reaches the log.
    before2 = log_path.stat().st_size
    _run_gate()
    after2 = log_path.stat().st_size
    appended = b""
    if after2 > before2:
        with open(log_path, "rb") as fh:
            fh.seek(before2)
            appended = fh.read()
    text = appended.decode(errors="ignore")
    markers = ("cycle 999", "cycle 1 ", "cycle 1\n", "sess-test",
               "refused-close-visible", "reviewer unreachable (test)", "test change")
    hit = [m for m in markers if m in text]
    assert not hit, (
        f"this test injected fabricated cycle(s) into the production governance log "
        f"({log_path}): {hit} found in the {after2 - before2} bytes appended — silence the "
        f"gate logger; the audit trail must only hold real cycles"
    )
    if after2 > before2:
        print(f"  PASS  silenced: 0 fabricated lines (another process appended "
              f"{after2 - before2} bytes meanwhile, none of them test traffic)")
    else:
        print(f"  PASS  silenced, the same run appended 0 bytes ({after2} bytes unchanged)")


if __name__ == "__main__":
    test_refused_close_visible()
    test_tests_do_not_pollute_the_production_log()
    print("\n✅ refused-close visibility checks passed")
    sys.exit(0)
