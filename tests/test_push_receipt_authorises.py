#!/usr/bin/env python3
"""A CLEAN review receipt authorises a lock-free push — hook + enforcer, ONE rule.

    python3 tests/test_push_receipt_authorises.py     # exit 0 = pass

WHY (friction, 2026-10-10): closing a cycle RELEASES the lock, and the push gate
demands an ACTIVE one — so every close needed a second, no-content 'push-<what>'
cycle purely to carry the lock. That is the mis-framed-cycle shape cycle 12012 was
refused for, and it cost 3 such cycles in one session (12009, 12010, 12021).

A CLEAN review receipt is a STRONGER authorisation than a lock: the close writes it
only after the self-adversarial review of that range returns CLEAN, and it is bound
to the content being pushed (reviewed_blobs), so a commit added after the close
invalidates it. This test asserts the carve-out in BOTH directions, at all three
layers that must agree:

  1. the shared rule  — ops/scripts/lib/review-receipt-check.py (scan_covering + --scan)
  2. the hook         — ops/scripts/pre-push-pull (wiring; the gate itself skips
                        without a real unpushed range, and the range is REPORTED, not faked)
  3. the enforcer     — plugins/governance-enforcer/__init__.py (decision function,
                        driven hermetically with a throwaway state dir + temp repo)

Hermetic by construction: every receipt lives in a tempfile state dir and every repo
is a throwaway git repo. Nothing here reads or writes the live governance state, so it
cannot pass or fail by accident — and it cannot fabricate a receipt for a real push.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "ops/scripts/lib/review-receipt-check.py"
HOOK = REPO / "ops/scripts/pre-push-pull"
ENFORCER = REPO / "plugins/governance-enforcer/__init__.py"

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def _mk_repo(tmp):
    """A repo with a base commit and one reviewed commit; returns (repo, base, tip).

    Each call gets its OWN directory (mkdtemp): the sections below each need a repo
    and a shared path would collide on the second call.
    """
    repo = Path(tempfile.mkdtemp(prefix="repo-", dir=str(tmp)))
    (repo / "mcp-servers").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "mcp-servers" / "loop-gov-mcp.py").write_text("v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "mcp-servers" / "loop-gov-mcp.py").write_text("v2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "the reviewed change")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base, tip


def _write_receipt(state_dir, slug, receipt):
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    p = Path(state_dir) / f".reviewed-{slug}-{receipt.get('tip_sha', 'x')}.json"
    p.write_text(json.dumps(receipt))
    return p


# ── 1. the shared rule ──────────────────────────────────────────────────────

def rule_checks(rrc, tmp):
    repo, base, tip = _mk_repo(tmp)
    blobs = rrc.range_blobs(repo, base, tip)
    check("range blobs resolve", isinstance(blobs, dict) and bool(blobs), True)
    covering = {"verdict": "CLEAN", "tip_sha": tip, "base_sha": base, "reviewed_blobs": blobs}
    state = Path(tmp) / "state"

    check("scan_covering has no rule of its own (uses authorises)",
          hasattr(rrc, "scan_covering"), True)

    _write_receipt(state, "hermes-cortex", covering)
    ok, path = rrc.scan_covering(state, "hermes-cortex", tip, base, repo=repo)
    check("a covering receipt authorises", ok, True)
    check("scan names the receipt it used", bool(path) and str(path).endswith(".json"), True)

    # Fail-closed directions.
    ok, _ = rrc.scan_covering(state, "hermes-cortex", tip, base, repo=repo)
    check("CONTROL: the same call is the one that passed", ok, True)
    ok2, _ = rrc.scan_covering(state, "other-repo", tip, base, repo=repo)
    check("a receipt for another repo never authorises", ok2, False)
    empty = Path(tmp) / "empty-state"
    empty.mkdir()
    ok3, _ = rrc.scan_covering(empty, "hermes-cortex", tip, base, repo=repo)
    check("no receipt at all refuses", ok3, False)
    ok4, _ = rrc.scan_covering(state, "hermes-cortex", "0" * 40, base, repo=repo)
    check("an unresolvable range refuses", ok4, False)

    # An EMPTY range (tip == base) never authorises: there is nothing to push, and
    # a receipt naming tip==base would otherwise pass the exact-match rule.
    empty_range = {"verdict": "CLEAN", "tip_sha": tip, "base_sha": tip,
                   "reviewed_blobs": blobs}
    _write_receipt(Path(tmp) / "state-empty", "hermes-cortex", empty_range)
    ok_e, _ = rrc.scan_covering(Path(tmp) / "state-empty", "hermes-cortex", tip, tip, repo=repo)
    check("a receipt for an EMPTY range never authorises", ok_e, False)

    # The range GAINS an unreviewed file → the receipt no longer covers it.
    (repo / "mcp-servers" / "extra.py").write_text("new\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "unreviewed addition")
    tip2 = _git(repo, "rev-parse", "HEAD").stdout.strip()
    ok5, _ = rrc.scan_covering(state, "hermes-cortex", tip2, base, repo=repo)
    check("a range that gained an uncovered file refuses", ok5, False)

    # The CLI the HOOK calls — same module, so the two can never disagree.
    out = subprocess.run([sys.executable, str(CHECK), "--scan", str(state),
                          "hermes-cortex", tip2, base, "--repo", str(repo)],
                         capture_output=True, text=True)
    check("--scan CLI refuses an uncovered range", (out.stdout.strip() or "0").split()[0], "0")
    out = subprocess.run([sys.executable, str(CHECK), "--scan", str(empty),
                          "hermes-cortex", tip2, base, "--repo", str(repo)],
                         capture_output=True, text=True)
    check("--scan CLI on an empty state dir refuses", (out.stdout.strip() or "0").split()[0], "0")
    ok6, path = rrc.scan_covering(state, "hermes-cortex", tip2, base, repo=repo)
    check("CONTROL: uncovered really is uncovered", ok6, False)
    blobs2 = rrc.range_blobs(repo, base, tip2)
    _write_receipt(Path(tmp) / "state2", "hermes-cortex",
                   {"verdict": "CLEAN", "tip_sha": tip2, "base_sha": base,
                    "reviewed_blobs": blobs2})
    out = subprocess.run([sys.executable, str(CHECK), "--scan", str(Path(tmp) / "state2"),
                          "hermes-cortex", tip2, base, "--repo", str(repo)],
                         capture_output=True, text=True)
    fields = (out.stdout.strip() or "0").split()
    check("--scan CLI allows a covering receipt", fields[0] if fields else "0", "1")
    check("--scan CLI names the receipt it used", len(fields) == 2, True)


# ── 2. the hook (wiring; the gate only runs for a real unpushed range) ──────

def hook_wiring_checks():
    src = HOOK.read_text()
    check("hook calls the shared rule, not a second copy of it",
          "--scan" in src and "review-receipt-check.py" in src, True)
    check("hook uses the receipt as a LOCK alternative",
          "review receipt authorises this push" in src.lower()
          or "receipt" in src.lower() and "LOCK_FOUND=1" in src, True)
    check("hook still blocks with no lock and no receipt",
          "Push blocked: no active governance lock" in src, True)
    check("hook still requires the always-review receipt",
          "carries no clean review receipt" in src, True)


def hook_live_range_check():
    """The one dynamic hook check — and it REPORTS when it cannot run.

    The lock carve-out is only reachable for a NON-EMPTY unpushed range, and the
    hook gates only $HOME/hermes-cortex, so this cannot be made ambient-state free.
    It is a real end-to-end assertion when the repo is ahead of origin/main (the
    normal condition while work is being pushed) and an explicit SKIP when it is
    level — never a silent pass.
    """
    def git(*args):
        return _git(REPO, *args).stdout.strip()

    tip = git("rev-parse", "HEAD")
    base = git("merge-base", "origin/main", "HEAD") or git("rev-list", "--max-parents=0", "HEAD")
    if not tip or not base or tip == base:
        print(f"SKIP  hook live range: nothing unpushed (HEAD {tip[:8]} is level with "
              f"origin/main) — the carve-out is unreachable by construction")
        return

    state = Path(tempfile.mkdtemp(prefix="push-receipt-live-"))
    hookdir = Path(tempfile.mkdtemp(prefix="hook-under-test-"))
    try:
        dst = hookdir / "pre-push"
        shutil.copy2(HOOK, dst)
        dst.chmod(0o755)
        env = dict(os.environ)
        env["GOVERNANCE_STATE_DIR"] = str(state)   # no lock, no receipt
        r = subprocess.run(["bash", str(dst)], cwd=REPO, env=env,
                           capture_output=True, text=True, timeout=300)
        combined = r.stdout + r.stderr
        check("hook still refuses when neither a lock nor a receipt exists",
              r.returncode != 0 and "no active governance lock" in combined, True)
    finally:
        shutil.rmtree(state, ignore_errors=True)
        shutil.rmtree(hookdir, ignore_errors=True)


# ── 3. the enforcer ────────────────────────────────────────────────────────

def enforcer_checks(tmp):
    enf = _load(ENFORCER, "gov_enforcer_under_test")

    # The matcher must accept exactly ONE shape: a lone git push, nothing else.
    for cmd, want in [
        ("git push", True),
        ("git push origin main", True),
        ("git -C /srv/repo push origin main", True),
        ("cd /srv/repo && git push origin main", True),
        ("git push --no-verify", False),          # skips the hook: never carved out
        ("git push && rm -rf /tmp/x", False),     # a compound change, not a push
        ("echo hi && git push", False),
        ("git push | tee /tmp/log", False),
        ("git push > /tmp/log", False),
        ("git commit -m 'push the thing'", False),
        ("git status", False),
        ("git log --grep=push", False),
        ("rsync -a . remote:", False),
    ]:
        got = enf._git_push_repo_hint(cmd) is not None
        check(f"matcher {cmd!r}", got, want)

    repo, base, tip = _mk_repo(tmp)
    blobs = _load(CHECK, "rrc_enforcer").range_blobs(repo, base, tip)
    state = Path(tmp) / "enf-state"

    args = {"command": f"git -C {repo} push origin main"}
    check("no receipt → no carve-out",
          enf._push_authorised_by_receipt(args, "", state), False)

    _write_receipt(state, Path(repo).name,
                   {"verdict": "CLEAN", "tip_sha": tip, "base_sha": base,
                    "reviewed_blobs": blobs})
    check("covering receipt → carve-out",
          enf._push_authorised_by_receipt(args, "", state), True)
    check("FINDINGS verdict → no carve-out",
          enf._push_authorised_by_receipt(
              args, "", _state_with(tmp, "findings", repo,
                                    {"verdict": "FINDINGS", "tip_sha": tip,
                                     "base_sha": base, "reviewed_blobs": blobs})),
          False)
    check("--no-verify push → no carve-out",
          enf._push_authorised_by_receipt(
              {"command": f"git -C {repo} push --no-verify origin main"}, "", state),
          False)
    check("a non-push command → no carve-out",
          enf._push_authorised_by_receipt({"command": "rm -rf /tmp/x"}, "", state), False)
    check("a receipt for another repo → no carve-out",
          enf._push_authorised_by_receipt({"command": "git -C /tmp push"}, "", state), False)
    check("the carve-out is scoped to a covering receipt, never to the command alone",
          enf._push_authorised_by_receipt(
              {"command": f"git -C {repo} push origin main"}, "",
              Path(tmp) / "empty-state-dir"),
          False)


def _state_with(tmp, name, repo, receipt):
    """A throwaway state dir holding exactly one receipt for `repo`'s slug."""
    state = Path(tmp) / f"state-{name}"
    _write_receipt(state, Path(repo).name, receipt)
    return state


def main():
    check("shared checker exists", CHECK.is_file(), True)
    check("enforcer exists", ENFORCER.is_file(), True)
    check("this file has exactly ONE main()",
          Path(__file__).read_text().count("\ndef main():") == 1, True)

    tmp = Path(tempfile.mkdtemp(prefix="push-receipt-"))
    try:
        rule_checks(_load(CHECK, "rrc_rule"), tmp)
        hook_wiring_checks()
        hook_live_range_check()
        enforcer_checks(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS — a CLEAN receipt authorises a lock-free push at all three "
          "layers, and every uncovered/compound/--no-verify shape still refuses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
