#!/usr/bin/env python3
"""Capture the evidence for the receipt / paused-cron fix into ONE committed transcript.

WHY: cycle 12515's close was REFUSED (5 high + 1 medium, all ``unverified-claim``) because
the evidence lived in the cycle note instead of inside the reviewed range. The reviewer
cannot see a terminal, so a claim about a RUN has to be a committed artifact.

Every block prints the command immediately above its output, then its rc measured BARE
(no pipe) - a piped ``rc=$?`` reports the pipe's last stage rather than the command's.

Re-runnable: ``python3 ops/scripts/manage/capture-crons-receipt-evidence.py``

Usage: python3 ops/scripts/manage/capture-crons-receipt-evidence.py [output-path]
"""

from __future__ import annotations

import getpass  # noqa: F401  (kept: normalise_line reads the user for ownership redaction)
import json  # noqa: F401  (kept: the probes below are quoted commands, not imports)
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
REPO = HOME / "hermes-cortex"
DEFAULT_OUT = REPO / "docs" / "evidence" / "fix-receipt-paused-crons-2026-10-14.txt"
HERMES_VENV = HOME / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"
ADV = HOME / ".hermes-cortex" / "scripts" / "adversarial-verify.py"

# The immutable range this artifact covers, pinned by revision so the before/after
# comparison is repeatable. EVIDENCE_BASE is the revision the range starts from — the
# PRE-FIX state, which is what makes "this was a regression / this was pre-existing"
# checkable at all — and EVIDENCE_COMMITS are the commits under review, so a reader sees
# which commit carried which file instead of inferring it from a whole-range diff.
# Short revisions here; the FULL resolved hashes are printed in the artifact.
EVIDENCE_BASE = "a128a8d2"
EVIDENCE_COMMITS = ("fe795f7b", "ccf9ed38", "fc5fff6c", "f566efe3")


def normalise_line(text: str, *, home: Path | None = None, user: str | None = None,
                   host: str | None = None) -> str:
    """Redact host identity and wall-clock noise from ONE emitted line.

    This runs in the GENERATOR, on every line, for two reasons: the transcript is
    committed to a PUBLIC repo (so home paths, the host name and `ls -l` ownership must
    not travel with it), and a hand-patched committed copy soon disagrees with the
    command printed above it.

    Deliberately narrow, so redaction cannot corrupt evidence:

    * the home directory becomes ``$HOME`` (and any *other* host's ``/home/<name>``
      becomes ``/home/<user>``), which keeps every command copy-pasteable;
    * ``Host: <name>`` becomes ``Host: <host>`` and ``@<host>`` becomes ``@<host>`` --
      NOT a bare replace of the host's name, which would mangle legitimate identifiers
      that share it (a DB role such as a reader account, or an agent's own name);
    * ``<user> <user>`` (the `ls -l` ownership column) becomes ``<user> <user>``;
    * pytest DURATIONS become ``<t>s``, because a wall-clock duration is noise no
      re-run can reproduce -- the verdict on that same line is the evidence.
    """
    home = HOME if home is None else home
    user = getpass.getuser() if user is None else user
    host = socket.gethostname() if host is None else host
    out = str(text)
    if home:
        out = out.replace(str(home), "$HOME")
    out = re.sub(r"/home/[A-Za-z0-9_.-]+", "/home/<user>", out)
    if user:
        out = re.sub(rf"\b{re.escape(user)}\s+{re.escape(user)}\b", "<user> <user>", out)
    out = re.sub(r"(?m)^(\s*)Host: \S+", r"\1Host: <host>", out)
    if host:
        out = re.sub(rf"@{re.escape(host)}\b", "@<host>", out)
    out = re.sub(r"\bin \d+(?:\.\d+)?s\b", "in <t>s", out)
    return out

# The homeassistant probe, run with the HERMES venv from its own root. It must call
# plugin discovery FIRST: a probe that skips it reports BOTH candidate toolset names
# invalid and blames the config - which is exactly how this session first mis-measured
# the warning and "fixed" it with a rename that removed capability.
HA_PROBE = '''
import sys, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.WARNING, format="LOG:%(message)s")
import hermes_cli.plugins as P
P.get_plugin_toolset_keys_nowait()          # plugin discovery FIRST
import hermes_cli.tools_config as tc
import toolsets
from hermes_cli.config import load_config_readonly
from toolsets import resolve_toolset
cfg = load_config_readonly()
pt = cfg.get("platform_toolsets") or {}
print("platform_toolsets.homeassistant present?", "homeassistant" in pt)
print("validate_toolset('homeassistant') ->", toolsets.validate_toolset("homeassistant"))
print("validate_toolset('hermes-homeassistant') ->", toolsets.validate_toolset("hermes-homeassistant"))
tc._warned_invalid_platform_toolsets.clear()
got = tc._get_platform_tools(cfg, "homeassistant")
tools = set()
for ts in got:
    try:
        tools |= set(resolve_toolset(ts))
    except Exception:
        pass
print("resolved toolsets:", len(got), "| ha_ tools:", sorted(t for t in tools if t.startswith("ha_")))
print("NOTE: a 'LOG:platform ... has no valid toolsets' line above means the warning FIRED;")
print("      its absence means it did not.")
'''

PROBE_CHECKS = (
    "import sys; sys.path.insert(0, " + repr(str(REPO / "ops/scripts/manage")) + ")\n"
    "from cortex_doctor.checks import check_paused_cron_reasons, check_orphan_cycle_resolution\n"
    "class R:\n"
    "    def __init__(self): self.rows = []\n"
    "    def add(self, name, status, detail='', fix=''):\n"
    "        self.rows.append((name, status, detail, fix))\n"
    "for fn in (check_paused_cron_reasons, check_orphan_cycle_resolution):\n"
    "    r = R(); fn(r)\n"
    "    for name, status, detail, fix in r.rows:\n"
    "        print(f'{name}: {status} - {detail}')\n"
    "        if fix: print('   fix:', fix)\n"
)

PROBE_PAUSED = (
    "import json, os, sqlite3\n"
    "p = os.path.expanduser('~/.hermes/cron/jobs.json')\n"
    "jobs = json.load(open(p)); jobs = jobs.get('jobs', jobs) if isinstance(jobs, dict) else jobs\n"
    "paused = [j for j in jobs if isinstance(j, dict) and (j.get('paused_at') or not j.get('enabled', True))]\n"
    "print('paused jobs:', len(paused))\n"
    "for j in paused:\n"
    "    print(' ', j.get('id'), j.get('name'), '| jobs.json paused_reason:', repr(j.get('paused_reason')))\n"
    "db = os.path.expanduser('~/.hermes/cron/notepad.db')\n"
    "con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)\n"
    "for job_id, value in con.execute(\"SELECT job_id, value FROM cron_notepad WHERE key='paused_reason'\"):\n"
    "    print('  notepad reason ->', job_id, '::', value[:180])\n"
)


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def emit(text: str) -> None:
        lines.append(normalise_line(text))

    def block(label: str, argv: list[str], cwd: Path | None = None, keep: str | None = None) -> None:
        """Run argv; print the command, its output and its BARE rc.

        keep: optional regex filtering the OUTPUT only (the rc is still the command's own).
        """
        emit(f"=== [{label}] $ {' '.join(argv)}")
        if cwd:
            emit(f"    (cwd: {cwd})")
        try:
            proc = subprocess.run(argv, cwd=str(cwd) if cwd else None,
                                  capture_output=True, text=True, timeout=900)
            body = (proc.stdout or "") + (proc.stderr or "")
            rc = proc.returncode
        except Exception as exc:  # a capture must never abort the whole artifact
            body, rc = f"COULD NOT RUN: {exc}", 127
        if keep:
            body = "\n".join(l for l in body.splitlines() if re.search(keep, l, re.I)) or "(no matching lines)"
        emit(body.rstrip("\n"))
        emit(f"--- rc={rc}")
        emit("")

    def capture(cmd: list[str]) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
        except Exception:
            return "?"

    emit("Evidence for the receipt / paused-cron fix. Captured by")
    emit("ops/scripts/manage/capture-crons-receipt-evidence.py - re-run that script (with an")
    emit("output path) to reproduce this file. Each block prints the command immediately")
    emit("above its output, then that command's OWN exit code, measured bare with no pipe.")
    emit("")
    emit("PROVENANCE: the revision range this run compares is named by the rev-parse block")
    emit("below. Volatile by design, and not claims about the change: the capture time, the")
    emit("pids in the process listing, and the pytest durations (normalised to <t>s). Every")
    emit("other line is reproducible from the same tree. Host identity is redacted here in")
    emit("the generator: $HOME for home paths, <host> for the host, <user> for file ownership.")
    emit("")
    emit(f"Host: {capture(['hostname', '-s'])}")
    emit(f"Captured: {capture(['date', '-u', '+%Y-%m-%d %H:%M:%S UTC'])}")
    emit("")
    for rev in ("HEAD", "HEAD~1", "origin/main", EVIDENCE_BASE):
        emit(f"{rev}: {capture(['git', '-C', str(REPO), 'rev-parse', rev])}")
    emit("")

    # 1. The doctor after the deploy: the new check, and 0 warn / 0 fail.
    block("doctor --quiet", ["python3", str(REPO / "ops/scripts/manage/cortex-doctor.py"), "--quiet"],
          keep=r"Paused crons|Orphan-cycle|Overall|⚠️|❌|ℹ️")

    # 2. The new check and its neighbour, called directly.
    block("checks in isolation", ["python3", "-c", PROBE_CHECKS])

    # 3. Paused crons: both recorded-reason stores.
    block("paused-cron reasons", ["python3", "-c", PROBE_PAUSED])

    # 4. The live cron prompt vs the committed installer — asked as a committed TEST,
    #    which is stronger evidence than a probe: the parser is driven with fixtures in
    #    both directions, then the live job is compared (skipping where it is not installed).

    # 5. homeassistant: warning gone, resolution unchanged.
    emit("=== homeassistant probe source (run with the Hermes venv python, cwd = its root)")
    emit(HA_PROBE.strip())
    emit("")
    block("homeassistant probe", [str(HERMES_VENV), "-c", HA_PROBE], cwd=HOME / ".hermes" / "hermes-agent")

    # 6. Tests: the new files, the wider selection, and the new file ALONE.
    pytest_py = capture(["bash", str(REPO / "ops/scripts/lib/python-with-module.sh"), "--print", "pytest"])
    emit(f"(pytest interpreter: {pytest_py})")
    emit("")
    two = ["tests/test_receipt_repo_identity.py", "tests/test_doctor_paused_cron_reasons.py",
           "tests/test_cron_prompt_matches_installer.py"]
    wider = two + [
        "tests/test_review_receipt_writer.py", "tests/test_review_receipt_gate.py",
        "tests/test_push_receipt_authorises.py", "tests/test_adversarial_error_swallow.py",
        "tests/test_backfill_legacy_reaper_cycles.py", "tests/test_bible_creative_model.py",
        "tests/test_doctor_env_consumers.py",
    ]
    base = ["env", "-u", "PYTHONPATH", "-u", "PYTHONHOME", pytest_py, "-m", "pytest"]
    block("live prompt vs installer (committed test)",
          base + ["tests/test_cron_prompt_matches_installer.py", "-q", "-p", "no:cacheprovider"], cwd=REPO)
    block("new tests", base + two + ["-q", "-p", "no:cacheprovider"], cwd=REPO)
    block("wider selection", base + wider + ["-q", "-p", "no:cacheprovider"], cwd=REPO)
    block("new file ALONE (the both-ways proof)",
          base + ["tests/test_doctor_paused_cron_reasons.py", "-q", "-p", "no:cacheprovider"], cwd=REPO)

    # 7. The adversarial gate, one invocation per changed file, each with its own rc.
    for rel, level in [
        ("mcp-servers/loop-gov-mcp.py", "A4"),
        ("ops/scripts/manage/cortex_doctor/checks.py", "A4"),
        ("ops/scripts/manage/cortex_doctor/cli.py", "A4"),
        ("ops/scripts/health/agent-cron-failure-watchdog.py", "A2"),
        ("ops/scripts/install/install-orch-crons.sh", "A2"),
        ("tests/test_receipt_repo_identity.py", "A2"),
        ("tests/test_doctor_paused_cron_reasons.py", "A2"),
        ("tests/test_cron_prompt_matches_installer.py", "A2"),
    ]:
        block(f"adversarial gate {level}",
              ["python3", str(ADV), "--file", rel, "--level", level, "--gate"], cwd=REPO,
              keep=r"Summary:|GATE_|finding|CRITICAL|HIGH|MEDIUM")

    # 8. Skill-drift parity: 0 stranded. --check COMPARES against the committed
    #    artifact and never writes it - without the flag this tool regenerates
    #    docs/evidence/skill-drift-parity.txt, so an evidence run would rewrite the
    #    tracked file it is measuring.
    block("skill drift parity (--check: compares, never writes)",
          ["python3", str(REPO / "ops/scripts/manage/check-skill-drift-parity.py"), "--check"],
          cwd=REPO, keep=r"stranded|in sync|Ver|artifact|^\-")

    # 9. deploy != load: the running MCP child predates the deployed file.
    block("deploy != load (MCP child vs deployed file)",
          ["bash", "-c", "ps -eo pid,lstart,etimes,args | grep -F loop-gov-mcp | grep -v grep; "
                         "ls -l --time-style=+%Y-%m-%dT%H:%M:%S "
                         f"{HOME}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"])

    # 10. The reserved word `column`, measured against the LIVE database with the
    #     prompt's OWN command form: quoted returns a row, unquoted must FAIL. Run
    #     both ways on purpose - an instruction "quote it" is only worth shipping if
    #     the unquoted form demonstrably breaks.
    for label, sql in (("QUOTED (must return a row)", 'SELECT "column" FROM tasks.tasks LIMIT 1'),
                       ("UNQUOTED (must fail)", "SELECT column FROM tasks.tasks LIMIT 1")):
        block(f"live DB: reserved word {label}",
              ["docker", "exec", "-i", "mycortex-postgres", "psql",
               "-U", "mycortex_reader_esther", "-d", "mycortex", "-c", sql])

    # 11. The commits in this range, ONE AT A TIME. The reviewer reads a RANGE diff, so
    #     a per-commit file list is what shows which commit carried the skill copy-back
    #     and which carried the addition on top — the ordering the copy-back rule depends
    #     on, and the one claim a whole-range diff cannot settle either way.
    for rev in EVIDENCE_COMMITS:
        block(f"files in commit {rev}",
              ["git", "show", "--stat", "--oneline", "--no-renames", rev], cwd=REPO)

    # 12. The PRE-FIX state, materialised from the immutable base revision in a detached
    #     worktree. A fix proves nothing without the failure it fixed, and that failure no
    #     longer exists in the working tree — so the two test files this range repaired are
    #     run where they were still broken, and the files whose failures this range did NOT
    #     cause are run there too, which is what separates "mine" from "pre-existing".
    base_wt = Path(tempfile.mkdtemp(prefix="evidence-baseline-"))
    block("baseline worktree at the range base (detached)",
          ["git", "worktree", "add", "--detach", str(base_wt), EVIDENCE_BASE], cwd=REPO)
    wt_pytest = capture(["bash", str(base_wt / "ops/scripts/lib/python-with-module.sh"),
                         "--print", "pytest"]).strip()
    emit(f"(baseline pytest interpreter: {wt_pytest})")
    emit("")
    if wt_pytest and wt_pytest != "?":
        wbase = ["env", "-u", "PYTHONPATH", "-u", "PYTHONHOME", wt_pytest,
                 "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", "--tb=no"]
        block("baseline: the two files this range REPAIRED (must FAIL there)",
              wbase + ["tests/test_agent_cron_failure_watchdog.py",
                       "tests/test_bible_verse_guard.py"], cwd=base_wt,
              keep=r"FAILED|ERROR|passed|failed|error")
        block("baseline: the failures this range did NOT cause (must FAIL there too)",
              wbase + ["tests/test_updater_robustness.py", "tests/test_repo_resource_paths.py",
                       "tests/test_retired_orch_crons.py", "tests/test_task_queue_evidence.py"],
              cwd=base_wt, keep=r"FAILED|passed|failed")
    else:
        emit("COULD NOT RUN: no pytest interpreter resolved from the baseline worktree")
    block("baseline worktree removed",
          ["git", "worktree", "remove", "--force", str(base_wt)], cwd=REPO)

    # 13. The read-only property with its OUTPUT VISIBLE (-s). The mode test's value is the
    #     printed before/after, which -q hides on a passing run: the reader must see that
    #     --check refused a missing baseline WITHOUT writing, and that the write mode wrote.
    block("the read-only parity test, output shown",
          base + ["tests/test_capture_evidence_readonly.py", "-q", "-s", "-p", "no:cacheprovider"],
          cwd=REPO, keep=r"refuses|write mode|wrote|passed|failed")

    emit("END OF EVIDENCE")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes, {len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
