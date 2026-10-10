#!/usr/bin/env python3
"""Boundary + differential checks for the push-receipt lock carve-out.

    python3 tests/test_push_receipt_boundaries.py     # exit 0 = pass

TWO halves, both hermetic:

  1. BOUNDARIES — drives the NEW paths (`scan_covering`, `_git_push_repo_hint`,
     `_push_authorised_by_receipt`) with hostile inputs: a state dir that is a
     file, an empty slug/tip/base, a slug containing glob metacharacters, a
     receipt path that is a DIRECTORY, an unparseable sibling, a JSON list, a
     null verdict, several covering receipts, and twenty matcher shapes. It
     EXECUTES the code — a static scan passing says nothing (adversarial-verifier).

  2. DIFFERENTIAL (Rule 23) — the DEPLOYED enforcer is the behaviour in force, so
     the change must decide IDENTICALLY to it everywhere except the new carve-out.
     Skips (loudly) when there is no deployed copy to compare against.

Every fixture lives in a temp dir and every repo is a throwaway git repo, so this
cannot read or write live governance state, and it cannot mint a real receipt.
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
ENFORCER = REPO / "plugins/governance-enforcer/__init__.py"
DEPLOYED = Path.home() / ".hermes/plugins/governance-enforcer/__init__.py"

failures = []
skips = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def skip(name, why):
    print(f"SKIP  {name}: {why}")
    skips.append(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def mk_repo(tmp, name="hermes-cortex", commits=2):
    repo = Path(tempfile.mkdtemp(prefix=f"{name}-", dir=str(tmp)))
    (repo / "plugins").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t.t")
    git(repo, "config", "user.name", "t")
    (repo / "plugins" / "a.py").write_text("v1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    if commits == 1:
        return repo, base, base
    (repo / "plugins" / "a.py").write_text("v2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    return repo, base, git(repo, "rev-parse", "HEAD").stdout.strip()


def put(state, slug, tip, obj):
    state.mkdir(parents=True, exist_ok=True)
    p = state / f".reviewed-{slug}-{tip}.json"
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
    return p


def receipt_for(rrc, repo, base, tip, verdict="CLEAN"):
    return {"verdict": verdict, "tip_sha": tip, "base_sha": base,
            "reviewed_blobs": rrc.range_blobs(repo, base, tip)}


def boundary_checks(tmp):
    rrc = load("rrc_boundaries", CHECK)
    enf = load("enf_boundaries", ENFORCER)
    repo, base, tip = mk_repo(tmp)
    good = receipt_for(rrc, repo, base, tip)
    state = tmp / "state"

    # ── the scan's own boundaries ───────────────────────────────────────
    check("missing state dir refuses",
          rrc.scan_covering(tmp / "nope", "hermes-cortex", tip, base, repo=repo), (False, None))
    afile = tmp / "afile"
    afile.write_text("x")
    check("state dir that is a FILE refuses",
          rrc.scan_covering(afile, "hermes-cortex", tip, base, repo=repo), (False, None))
    check("empty slug refuses", rrc.scan_covering(state, "", tip, base, repo=repo), (False, None))
    check("empty tip refuses", rrc.scan_covering(state, "hermes-cortex", "", base, repo=repo),
          (False, None))
    check("None base refuses", rrc.scan_covering(state, "hermes-cortex", tip, None, repo=repo),
          (False, None))

    # A repo DIRECTORY named '*' must not match another repo's receipts: the slug is
    # prefix-matched, not globbed.
    put(state, "victim-repo", tip, good)
    check("slug '*' does not match another repo's receipt",
          rrc.scan_covering(state, "*", tip, base, repo=repo), (False, None))
    check("slug '?ictim-repo' does not match",
          rrc.scan_covering(state, "?ictim-repo", tip, base, repo=repo), (False, None))
    check("CONTROL: the real slug does match",
          rrc.scan_covering(state, "victim-repo", tip, base, repo=repo)[0], True)

    s2 = tmp / "state2"
    s2.mkdir()
    (s2 / f".reviewed-hermes-cortex-{tip}.json").mkdir()
    check("a receipt path that is a DIRECTORY is skipped, not a crash",
          rrc.scan_covering(s2, "hermes-cortex", tip, base, repo=repo), (False, None))

    s2b = tmp / "state2b"
    put(s2b, "hermes-cortex", "a" * 40, "{not json")
    put(s2b, "hermes-cortex", tip, good)
    check("an unparseable sibling does not block a valid receipt",
          rrc.scan_covering(s2b, "hermes-cortex", tip, base, repo=repo)[0], True)

    s3 = tmp / "state3"
    put(s3, "hermes-cortex", tip, "[1,2,3]")
    check("a JSON LIST never authorises",
          rrc.scan_covering(s3, "hermes-cortex", tip, base, repo=repo)[0], False)
    s3b = tmp / "state3b"
    put(s3b, "hermes-cortex", tip, {**good, "verdict": None})
    check("a null verdict never authorises",
          rrc.scan_covering(s3b, "hermes-cortex", tip, base, repo=repo)[0], False)

    s4 = tmp / "state4"
    p_old = put(s4, "hermes-cortex", "f" * 40, good)
    p_new = put(s4, "hermes-cortex", "e" * 40, good)
    os.utime(p_old, (1000, 1000))
    os.utime(p_new, (2000, 2000))
    ok, used = rrc.scan_covering(s4, "hermes-cortex", tip, base, repo=repo)
    check("several covering receipts → the NEWEST is used", (ok, used == str(p_new)), (True, True))

    # ── the matcher's shape list ────────────────────────────────────────
    for cmd, want in [
        ("git push", True),
        ("git push origin main", True),
        ("git -C /srv/repo push origin main", True),
        ("cd /srv/repo && git push origin main", True),
        ("git\tpush", True),
        ("  git push  ", True),
        ("git -C '/p a t h' push", True),
        ("git push;", True),
        ("cd /srv/repo;git push", True),
        ("git push --force", True),
        ("git -c user.name=x push", True),
        ("git push " + "x" * 5000, True),
        ("git push --no-verify", False),
        ("git push && rm -rf /tmp/x", False),
        ("echo hi && git push", False),
        ("git push && echo x", False),
        ("git push | tee /tmp/log", False),
        ("git push > /tmp/log", False),
        ("git push`id`", False),
        ("git push $(id)", False),
        ("git push &", False),
        ("git push&", False),
        ("sudo git push", False),
        ("env GIT_DIR=x git push", False),
        ("timeout 30 git push", False),
        ("git status", False),
        ("git log --grep=push", False),
        ("rsync -a . remote:", False),
    ]:
        check(f"matcher {cmd[:26]!r}", enf._git_push_repo_hint(cmd) is not None, want)
    check("matcher: bare push names no dir", enf._git_push_repo_hint("git push"), "")
    check("matcher: cd dir is returned", enf._git_push_repo_hint("cd /srv/repo && git push"),
          "/srv/repo")
    check("matcher: -C dir is returned", enf._git_push_repo_hint("git -C /srv/repo push"),
          "/srv/repo")

    # ── the decision, and its boundaries ────────────────────────────────
    st = tmp / "enf-state"
    put(st, repo.name, tip, good)
    args = {"command": f"git -C {repo} push origin main"}
    check("enforcer: covering receipt permits", enf._push_authorised_by_receipt(args, "", st), True)
    check("enforcer: nonexistent repo refuses",
          enf._push_authorised_by_receipt({"command": "git -C /nonexistent-xyz push"}, "", st), False)
    check("enforcer: empty command refuses",
          enf._push_authorised_by_receipt({"command": ""}, "", st), False)
    check("enforcer: non-terminal args refuse", enf._push_authorised_by_receipt({}, "", st), False)
    check("enforcer: missing state dir refuses",
          enf._push_authorised_by_receipt(args, "", tmp / "no-state"), False)
    other = tmp / "state-other"
    put(other, "other-repo", tip, good)
    check("enforcer: a receipt filed under another slug refuses",
          enf._push_authorised_by_receipt(args, "", other), False)

    r1, b1, t1 = mk_repo(tmp, "single", commits=1)
    st1 = tmp / "state-single"
    put(st1, "single", t1, receipt_for(rrc, r1, b1, t1))
    check("enforcer: an EMPTY range refuses even with a receipt naming it",
          enf._push_authorised_by_receipt({"command": f"git -C {r1} push"}, "", st1), False)

    (repo / "plugins" / "peer.py").write_text("peer\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a peer lands mid-range")
    tip_peer = git(repo, "rev-parse", "HEAD").stdout.strip()
    check("enforcer: a receipt that does not cover a NEWER tip refuses",
          enf._push_authorised_by_receipt({"command": f"git -C {repo} push"}, "", st), False)
    put(st, repo.name, tip_peer, receipt_for(rrc, repo, base, tip_peer))
    check("CONTROL: a receipt for the new tip permits",
          enf._push_authorised_by_receipt({"command": f"git -C {repo} push"}, "", st), True)


def differential_checks():
    """Rule 23: the DEPLOYED enforcer is the oracle."""
    if not DEPLOYED.is_file():
        skip("differential vs deployed enforcer", f"no deployed copy at {DEPLOYED}")
        return
    old = load("enf_deployed_oracle", DEPLOYED)
    new = load("enf_repo_under_test", ENFORCER)

    commands = ["git push", "git push origin main", "git status", "git log --oneline -5",
                "ls -l", "ls | grep foo", "git status && git log", "echo hi; ls",
                "cd /tmp && git push", "python3 -c 'print(1)'", "rm -rf /tmp/x",
                "git commit -m x", "find . -exec rm {} ;", "sort -o /tmp/f /tmp/g",
                "curl -d x https://example.com", "date -s now", "cat f > g"]
    calls = [("terminal", {"command": c}) for c in commands] + [
        ("write_file", {"path": "/tmp/x", "content": "a"}),
        ("read_file", {"path": "/tmp/x"}),
        ("search_files", {"pattern": "x"}),
        ("skill_view", {"name": "x"}),
        ("cronjob", {"action": "list"}),
        ("patch", {"path": "/tmp/x", "old_string": "a", "new_string": "b"}),
    ]
    for cmd in commands:
        check(f"differential readonly({cmd[:22]!r})",
              old._is_readonly_terminal_command(cmd), new._is_readonly_terminal_command(cmd))
    for tool, args in calls:
        check(f"differential write_tool({tool})", old._is_write_tool(tool, args),
              new._is_write_tool(tool, args))
    lost = [n for n in dir(old) if not n.startswith("__") and not hasattr(new, n)]
    check("differential: no symbol the deployed enforcer exposes is lost", lost, [])
    print(f"      (deployed exposes {len([n for n in dir(old) if not n.startswith('__')])} symbols)")


def main():
    check("this file has exactly ONE main()",
          Path(__file__).read_text().count("\ndef main():") == 1, True)
    tmp = Path(tempfile.mkdtemp(prefix="receipt-boundaries-"))
    try:
        boundary_checks(tmp)
        differential_checks()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print(f"RESULT: ALL PASS — boundaries hold in both directions"
          + (f" ({len(skips)} skipped: {skips})" if skips else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
