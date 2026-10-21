#!/usr/bin/env python3
"""A deferred doctor warning must be a RECORDED decision, and deferring must be cheap.

Operator, 2026-10-20: "I'm getting tired of seeing agents just gloss over the warnings after a
cortex update. Can we encourage the agents to fix warnings and info too? I don't want mandatory,
however, I don't want them to just ignore it every time."

What this file pins, in the order it matters:

  A. a record is REFUSED when it is not a decision — an unknown disposition, no owner, no reason,
     a check name that is not in the current run, or `fixed` claimed while the check still warns.
     (Review findings ADV-0-1 and ADV-0-3: the point is a decision with a name on it, and "fixed"
     must not become a way to hide a live warning.)
  B. a live disposition takes its check out of the undisposed set, and nothing else moves.
  C. a disposition EXPIRES: past the TTL it is reported STALE and counts as undisposed again, so
     deferral is renewed rather than eternal.
  D. the READ path fails SOFT — a missing, corrupt or wrongly-shaped store reports everything as
     undisposed, and never stops a doctor run. The WRITE path is the opposite (F).
  E. the rendering says so out loud: the summary carries the undisposed count, the block names each
     undisposed check with its own fix hint and the exact record command, and a disposed check
     prints its label.
  F. an explicit `--disposition` write that cannot land FAILS LOUDLY (review finding ADV-0-2): a
     silent success would tell the caller a decision was recorded that was not.
  G. end to end through the real CLI in a subprocess: a refused record exits non-zero and says why,
     and listing an empty store exits 0.

No test touches the live doctor state: every store here is a temp path, and the one CLI run is
given its own HERMES_CORTEX_HOME.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "ops" / "scripts" / "manage" / "cortex_doctor"

# The doctor is a package (`cortex_doctor`) whose modules use relative imports, so the test loads
# the REAL modules through the package rather than by file path: a by-path load would break
# `from .config import CORTEX_HOME` and prove nothing about what runs.
sys.path.insert(0, str(PKG.parent))
from cortex_doctor import dispositions as disp_pkg  # noqa: E402
from cortex_doctor import results as results_pkg  # noqa: E402

_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


def _refuses(fn, *a, **kw) -> str:
    """Return the refusal message, or "" when the call was allowed."""
    try:
        fn(*a, **kw)
    except disp_pkg.DispositionError as e:
        return str(e)
    return ""


def test_a_a_record_must_be_a_decision() -> None:
    print("A. a record that is not a decision is refused")
    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "d.json"
        checks = [{"name": "Skill drift", "status": "WARN", "detail": "", "fix": "run x"},
                  {"name": "Repo clean", "status": "PASS", "detail": "", "fix": ""}]
        msg = _refuses(disp_pkg.record, "Skill drift", "whatever", "esther", "why", path=store,
                       checks=checks)
        _check("an unknown disposition is refused", "must be one of" in msg, msg)
        msg = _refuses(disp_pkg.record, "Skill drift", "deferred", "", "why", path=store,
                       checks=checks)
        _check("no owner is refused (ADV-0-1)", "--owner is required" in msg, msg)
        msg = _refuses(disp_pkg.record, "Skill drift", "deferred", "esther", "  ", path=store,
                       checks=checks)
        _check("no reason is refused", "--reason is required" in msg, msg)
        msg = _refuses(disp_pkg.record, "No Such Check", "deferred", "esther", "why", path=store,
                       checks=checks)
        _check("a check name that is not in this run is refused", "no check named" in msg, msg)
        msg = _refuses(disp_pkg.record, "Skill drift", "fixed", "esther", "why", path=store,
                       checks=checks)
        _check("`fixed` on a check that still warns is refused (ADV-0-3)",
               "currently WARN" in msg and "false claim" in msg, msg)
        _check("none of the refused records wrote anything", not store.exists(),
               "a refused record must leave no trace")


def test_b_a_live_disposition_removes_only_its_check() -> None:
    print("B. a live disposition clears its own check and nothing else")
    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "d.json"
        checks = [{"name": "Skill drift", "status": "WARN", "detail": "", "fix": "x"},
                  {"name": "AGENTS.md size", "status": "WARN", "detail": "", "fix": "y"},
                  {"name": "Repo clean", "status": "PASS", "detail": "", "fix": ""}]
        before = disp_pkg.undisposed(checks, disp_pkg.load(store))
        _check("everything starts undisposed", [c["name"] for c in before] ==
               ["Skill drift", "AGENTS.md size"], str(before))
        disp_pkg.record("Skill drift", "deferred", "esther", "tracked as its own cycle",
                        path=store, checks=checks)
        after = disp_pkg.undisposed(checks, disp_pkg.load(store))
        _check("the recorded check is no longer undisposed",
               [c["name"] for c in after] == ["AGENTS.md size"], str(after))
        _check("the other warning still is", after and after[0]["name"] == "AGENTS.md size")
        _check("a PASS check is never listed either way",
               all(c["status"] != "PASS" for c in after))
        _check("state_for reads it as disposed",
               disp_pkg.state_for("Skill drift", disp_pkg.load(store)) == "disposed")
        _check("and it round-trips through the file",
               disp_pkg.load(store)["Skill drift"]["owner"] == "esther")


def test_c_a_disposition_expires() -> None:
    print("C. a disposition expires and must be renewed")
    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "d.json"
        checks = [{"name": "Skill drift", "status": "WARN", "detail": "", "fix": "x"}]
        disp_pkg.record("Skill drift", "deferred", "esther", "later", path=store, checks=checks)
        now = datetime.now(timezone.utc)
        _check("fresh is disposed",
               disp_pkg.state_for("Skill drift", disp_pkg.load(store), now) == "disposed")
        old = now + timedelta(days=disp_pkg.TTL_DAYS + 1)
        _check("past the TTL it is STALE",
               disp_pkg.state_for("Skill drift", disp_pkg.load(store), old) == "stale")
        _check("and STALE counts as undisposed again",
               len(disp_pkg.undisposed(checks, disp_pkg.load(store), old)) == 1,
               "a stale disposition must not keep hiding the warning")
        _check("the label says to renew it",
               "STALE" in disp_pkg.describe("Skill drift", disp_pkg.load(store), old))


def test_d_the_read_path_fails_soft() -> None:
    print("D. the read path fails soft — a doctor run must never die on this store")
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "nope.json"
        _check("a missing store is empty", disp_pkg.load(missing) == {})
        corrupt = Path(td) / "corrupt.json"
        corrupt.write_text("{not json")
        _check("corrupt JSON is empty", disp_pkg.load(corrupt) == {})
        wrong = Path(td) / "wrong.json"
        wrong.write_text(json.dumps(["not", "a", "dict"]))
        _check("a wrongly-shaped store is empty", disp_pkg.load(wrong) == {})
        _check("so everything is undisposed",
               len(disp_pkg.undisposed([{"name": "x", "status": "WARN"}], disp_pkg.load(corrupt))) == 1)
        _check("an entry with no date cannot be aged, so it is STALE not trusted",
               disp_pkg.state_for("x", {"x": {"disposition": "deferred", "owner": "e"}}) == "stale")


def test_e_the_rendering_says_so() -> None:
    print("E. the rendering names what nobody has decided")
    res = results_pkg.Results()
    res.add("Skill drift", "WARN", "3 drifted", "Run: cortex-doctor.py")
    res.add("Repo clean", "PASS", "clean")
    res.add("Some info", "INFO", "fyi")
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        res.print_summary(compact=True)          # COMPACT: --quiet is what the update path runs
    out = buf.getvalue()
    _check("the summary carries the undisposed count", "2 undisposed" in out, out[:400])
    _check("the block names the undisposed check", "Skill drift" in out)
    _check("it carries that check's own fix hint", "Run: cortex-doctor.py" in out)
    _check("it carries the exact record command", "--disposition \"Skill drift\"" in out)
    _check("INFO counts too (the operator asked for warnings AND info)", "Some info" in out)
    _check("a PASS check is not listed as undisposed", "Repo clean" not in out.split("UNDISPOSED")[1])

    res.dispositions = {"Skill drift": {"disposition": "deferred", "owner": "esther",
                                       "reason": "tracked", "recorded_at":
                                       datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}}
    buf = io.StringIO()
    with redirect_stdout(buf):
        res.print_summary(compact=True)
    out2 = buf.getvalue()
    _check("a disposed check prints its label in the run", "[deferred (esther, since" in out2,
           out2[:400])
    _check("and drops out of the undisposed count", "1 undisposed" in out2, out2[:400])


def test_f_a_failed_write_is_loud() -> None:
    print("F. an explicit write that cannot land FAILS LOUDLY (ADV-0-2)")
    with tempfile.TemporaryDirectory() as td:
        blocker = Path(td) / "not-a-dir"
        blocker.write_text("a file, so mkdir underneath it must fail")
        target = blocker / "d.json"
        checks = [{"name": "Skill drift", "status": "WARN", "detail": "", "fix": "x"}]
        msg = _refuses(disp_pkg.record, "Skill drift", "deferred", "esther", "why",
                       path=target, checks=checks)
        _check("the write refusal is raised, not swallowed", "could not write" in msg, msg)


def test_g_end_to_end_through_the_cli() -> None:
    print("G. the CLI: a refused record exits non-zero and says why; an empty store lists as empty")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "HERMES_CORTEX_HOME": td}
        # A record for a check that cannot exist must fail visibly (this runs the quick check set).
        r = subprocess.run([sys.executable, str(REPO / "ops" / "scripts" / "manage" /
                                               "cortex-doctor.py"),
                            "--quick", "--disposition", "No Such Check", "--as", "deferred",
                            "--owner", "tester", "--reason", "test"],
                           capture_output=True, text=True, env=env, cwd=str(REPO), timeout=900)
        _check("a refused record exits non-zero", r.returncode != 0, f"rc={r.returncode}")
        _check("and names the refusal on stderr", "no check named" in r.stderr, r.stderr[-400:])
        _check("nothing was written", not (Path(td) / "state" / "doctor-dispositions.json").exists())
        # Listing an empty store is a clean, quiet exit.
        r2 = subprocess.run([sys.executable, str(REPO / "ops" / "scripts" / "manage" /
                                                "cortex-doctor.py"), "--dispositions"],
                            capture_output=True, text=True, env=env, cwd=str(REPO), timeout=300)
        _check("listing an empty store exits 0", r2.returncode == 0, f"rc={r2.returncode}")
        _check("and says every check is undisposed", "UNDISPOSED" in r2.stdout, r2.stdout[-300:])


if __name__ == "__main__":
    for fn in (test_a_a_record_must_be_a_decision, test_b_a_live_disposition_removes_only_its_check,
               test_c_a_disposition_expires, test_d_the_read_path_fails_soft,
               test_e_the_rendering_says_so, test_f_a_failed_write_is_loud,
               test_g_end_to_end_through_the_cli):
        fn()
    print(f"\n{'FAIL' if _F else 'ALL PASS'} ({len(_F)} failed)")
    sys.exit(1 if _F else 0)
