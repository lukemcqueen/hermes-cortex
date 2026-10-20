#!/usr/bin/env python3
"""Shell portability guards — the traps that break macOS but pass on Linux.

Two checks, because a lesson in prose does not stop the next agent:

1. NO HEREDOC INSIDE $( )  (static, always runs).
   A heredoc nested in a command substitution is a bash 3.2 parser trap: an
   apostrophe anywhere in the body — a comment reading "this session's activity" is
   enough — makes 3.2 mis-count the quotes and refuse to parse the WHOLE script.
   bash 5.x parses it happily, so it passes every Linux test and then blocks every
   commit on macOS. Measured 2026-10-20 on ops/scripts/prepare-commit-msg-session:
   bash 3.2 -> "unexpected EOF while looking for matching `''" (rc=2), bash 5.2 -> rc=0.
   The fix is never "remove the apostrophe" — that leaves the landmine armed — it is
   to take the heredoc OUT of the substitution (redirect to a temp file, then read it).

2. THE HOOKS PARSE UNDER REAL BASH 3.2  (runs when a bash 3.2 is reachable).
   `bash -n` under 3.2 is the authority: it also catches unbalanced quotes and
   bash-4-only syntax that this static rule cannot see. Needs docker + the image;
   SKIPS loudly with the enabling command when either is missing, because a check
   that silently reports nothing is worse than no check.

Scope: shell scripts that can EXECUTE on a host — every shell script in the deploy map
(`register "..."` in cortex-update.sh), the git hook symlinks in `hooks/`, and the hook
IMPLEMENTATIONS those symlinks point at in `ops/scripts/`. Repo-only
tooling (ops/evidence one-off record scripts, cutover artefacts) is deliberately out
of scope: it never leaves this repo, so a macOS parser never sees it. Widening the
scan to "everything with a shebang" would report armed-but-unreachable sites and
teach readers to ignore the guard.

Run: python3 tests/test_shell_portability.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UPDATE_SH = REPO / "ops" / "scripts" / "cortex-update.sh"
# Hook IMPLEMENTATIONS — the files the git hooks symlink to (hooks/pre-commit →
# scripts/pre-commit-score, etc.). They are not hook NAMES; the hooks/ directory scan
# covers the symlinks themselves, and these names cover their targets in ops/scripts/.
HOOK_IMPL_NAMES = ("pre-commit-score", "pre-push-pull", "post-commit-audit",
                   "post-push-audit", "prepare-commit-msg-session")
BASH32_IMAGE = "bash:3.2"

failures: list[str] = []
skips: list[str] = []       # disclosed in the summary: a skip is not a silent pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def _is_shell(path: Path) -> bool:
    try:
        head = path.open("rb").read(80)
    except OSError:
        return False
    return head.startswith(b"#!") and bool(re.search(rb"#!.*\b(bash|sh|dash)\b", head))


def shell_scripts() -> list[Path]:
    """Every shell script that the deploy map ships, plus the git hooks themselves."""
    out: set[Path] = set()
    try:
        registered = re.findall(r'^(?:register|register_orch)\s+"([^"]+)"', UPDATE_SH.read_text(), re.M)
    except OSError:
        registered = []
    for rel in registered:
        cand = REPO / rel
        if cand.is_file() and _is_shell(cand):
            out.add(cand)
    hooks_dir = REPO / "hooks"
    if hooks_dir.is_dir():
        for p in hooks_dir.rglob("*"):
            if p.is_file() and _is_shell(p):
                out.add(p)
    for name in HOOK_IMPL_NAMES:
        for cand in (REPO / "ops" / "scripts" / name,):
            if cand.is_file() and _is_shell(cand):
                out.add(cand)
    return sorted(out)


def heredocs_inside_substitution(text: str) -> list[tuple[int, str]]:
    """A heredoc start while — or on the same line as opening — a $( ) substitution."""
    hits: list[tuple[int, str]] = []
    depth = 0
    for n, line in enumerate(text.splitlines(), 1):
        # `)` is not always a substitution close: `$(( … ))` consumes two, and a case arm
        # terminator sits alone at the start of a line. Counting those as closes drives
        # depth to zero early and lets a real offender SLIP THROUGH — the one direction
        # this guard must never fail in.
        arithmetic = line.count("$((")
        closes = line.count(")") - 2 * arithmetic
        if line.lstrip().startswith(")"):
            closes -= 1
        # A COMMENT cannot change how the script parses, so prose describing the trap
        # (including this file's own guidance elsewhere) must not be flagged. The trap
        # lives in CODE — which is also why the apostrophe that broke the hook was in
        # a comment inside the heredoc BODY: that body is data, not shell.
        if line.lstrip().startswith("#"):
            continue
        opens = line.count("$(")
        if re.search(r"<<-?\s*['\"]?[A-Za-z_]", line) and (depth > 0 or opens > 0):
            hits.append((n, line.strip()[:100]))
        opens = opens - arithmetic
        depth += opens - closes
        if depth < 0:
            depth = 0
    return hits


def test_no_heredoc_inside_command_substitution() -> None:
    offenders: list[str] = []
    for path in shell_scripts():
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for line_no, line in heredocs_inside_substitution(text):
            offenders.append(f"{path.relative_to(REPO)}:{line_no}: {line}")
    check(not offenders,
          "a heredoc inside $( ) breaks bash 3.2 (macOS) — move it out of the "
          "substitution (redirect to a temp file, then read that):\n    "
          + "\n    ".join(offenders))


def test_detector_sees_the_known_bad_shape() -> None:
    """The guard must be able to SEE the defect it forbids.

    Without this, a detector that silently matches nothing passes forever.
    """
    bad = 'X="$(python3 - "$A" <<\'PY\' 2>/dev/null || true\nprint(1)\nPY\n)"\n'
    good = '_T="$(mktemp)"\npython3 - "$A" <<\'PY\' >"$_T" 2>/dev/null || true\nprint(1)\nPY\n'
    check(bool(heredocs_inside_substitution(bad)),
          "the detector did not flag a heredoc written inside $( ) — it is blind")
    check(not heredocs_inside_substitution(good),
          "the detector flagged the SAFE shape (heredoc with a plain redirect)")
    prose = '# never write X="$(cmd <<PY" — it breaks bash 3.2\n'
    check(not heredocs_inside_substitution(prose),
          "the detector flagged a COMMENT that merely describes the trap — prose is not code")


def _registered_shell_scripts() -> list[Path]:
    """The shell scripts the deploy map ships — read from cortex-update.sh itself."""
    try:
        registered = re.findall(r'^(?:register|register_orch)\s+"([^"]+)"',
                                UPDATE_SH.read_text(), re.M)
    except OSError:
        return []
    out = []
    for rel in registered:
        cand = REPO / rel
        if cand.is_file() and _is_shell(cand):
            out.append(cand)
    return out


def _have_docker_image() -> bool:
    """True when the bash 3.2 image is usable — and SAY WHY when it is not.

    A non-zero `docker image inspect` covers two very different situations: the image is
    absent (pull it) and the daemon is unreachable (something else is wrong). Reporting
    both as a silent skip would hide a broken docker behind a missing image.
    """
    if not shutil.which("docker"):
        print("SKIP  bash 3.2 parse gate: no docker on PATH "
              f"(install docker, or enable the gate elsewhere: docker pull {BASH32_IMAGE})")
        return False
    try:
        proc = subprocess.run(["docker", "image", "inspect", BASH32_IMAGE],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"SKIP  bash 3.2 parse gate: could not run docker ({type(e).__name__}: {e})")
        return False
    if proc.returncode == 0:
        return True
    err = (proc.stderr or "").strip().splitlines()
    detail = err[0] if err else f"rc={proc.returncode}"
    if "no such image" in detail.lower() or "no such object" in detail.lower():
        print(f"SKIP  bash 3.2 parse gate: image absent — enable with: docker pull {BASH32_IMAGE}")
        skips.append(f"bash 3.2 parse gate — image absent (docker pull {BASH32_IMAGE})")
    else:
        print(f"SKIP  bash 3.2 parse gate: docker could not inspect the image "
              f"({detail}) — this is NOT the same as the image being missing")
        skips.append(f"bash 3.2 parse gate — docker inspect failed ({detail})")
    return False


def test_scripts_parse_under_real_bash_3_2() -> None:
    scripts = shell_scripts()
    # No magic count: assert the resolver found each thing it CLAIMS to cover, and
    # derive the deploy-map side from the map itself. A hardcoded ">= 20" would fail a
    # healthy repo that legitimately ships fewer scripts, which teaches readers to
    # ignore the guard.
    names = {p.name for p in scripts}
    missing_impls = [n for n in HOOK_IMPL_NAMES if n not in names]
    check(not missing_impls,
          f"the scope resolver missed hook implementation(s) {missing_impls} "
          f"(resolved {len(scripts)}: {sorted(names)[:8]}…) — fix the resolver")
    registered_shells = _registered_shell_scripts()
    check(bool(registered_shells),
          "no shell script from the deploy map resolved — the map parser or the paths "
          "changed, so this guard would silently scan almost nothing")
    missing_mapped = [str(p.relative_to(REPO)) for p in registered_shells if p not in scripts]
    check(not missing_mapped,
          f"deploy-map script(s) not in the scan set: {missing_mapped}")
    print(f"  scanning {len(scripts)} script(s): {len(registered_shells)} from the deploy "
          f"map + {len(HOOK_IMPL_NAMES)} hook implementations + hooks/")
    if not _have_docker_image():
        return   # the probe already printed WHY (absent image vs unreachable daemon)
    # One container, one pass: bash -n every script under the real macOS shell.
    script = ("fail=0\n"
              "while IFS= read -r f; do\n"
              '  bash -n "$f" 2>/tmp/err || { printf "FAIL %s: %s\\n" "${f#/repo/}" '
              '"$(head -1 /tmp/err)"; fail=$((fail+1)); }\n'
              'done < /tmp/list\n'
              'echo "FAILURES=$fail"\n')
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="bash32-check-"))
    (tmp / "list").write_text("\n".join(str(p) for p in scripts) + "\n")
    (tmp / "run.sh").write_text(script)
    try:
        proc = subprocess.run(
            ["docker", "run", "--rm",
             "-v", f"{REPO}:/repo:ro",
             "-v", f"{tmp}:/check:ro",
             BASH32_IMAGE, "bash", "/check/run.sh"],
            capture_output=True, text=True, timeout=600)
        out = (proc.stdout or "") + (proc.stderr or "")
        fails = [l for l in out.splitlines() if l.startswith("FAIL ")]
        check(not fails,
              "these scripts do not parse under bash 3.2 (macOS) — they would block "
              "every commit/run on a Mac:\n    " + "\n    ".join(fails))
        check("FAILURES=0" in out, f"the bash 3.2 pass did not complete cleanly: {out[-300:]}")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"SKIP  bash 3.2 parse gate: could not run docker ({type(e).__name__}: {e})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_detector_sees_the_known_bad_shape()
    test_no_heredoc_inside_command_substitution()
    test_scripts_parse_under_real_bash_3_2()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    detail = f"; SKIPPED: {'; '.join(skips)}" if skips else "; bash 3.2 parse gate clean"
    print(f"PASS: no heredoc inside $( ) in {len(shell_scripts())} shell scripts{detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
