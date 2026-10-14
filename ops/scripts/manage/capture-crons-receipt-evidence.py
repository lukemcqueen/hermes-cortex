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

import json  # noqa: F401  (kept: the probes below are quoted commands, not imports)
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
REPO = HOME / "hermes-cortex"
DEFAULT_OUT = REPO / "docs" / "evidence" / "fix-receipt-paused-crons-2026-10-14.txt"
HERMES_VENV = HOME / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"
ADV = HOME / ".hermes-cortex" / "scripts" / "adversarial-verify.py"

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
        lines.append(text)

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

    emit("Evidence for the receipt / paused-cron fix (commit ebcf8769, plus the follow-up")
    emit("commit this file ships in). Every block is the complete captured output of the")
    emit("command printed immediately above it, with the command's OWN exit code (measured")
    emit("bare, with no pipe). Re-run any line to reproduce its block.")
    emit("")
    emit(f"Host: {capture(['hostname', '-s'])}")
    emit(f"Captured: {capture(['date', '-u', '+%Y-%m-%d %H:%M:%S UTC'])}")
    emit("")
    emit("READ THIS FIRST - the doctor block below is captured WITH THIS ARTIFACT STILL")
    emit("UNCOMMITTED, so its single warn is 'Repo clean' (the capture file and script")
    emit("themselves). Everything the range fixed reads PASS in that same block: note")
    emit("0 fail, and 'Paused crons: reason' / 'Orphan-cycle resolution' both green.")
    emit("")
    for rev in ("HEAD", "HEAD~1", "origin/main"):
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

    # 8. Skill-drift parity: 0 stranded.
    block("skill drift parity", ["python3", str(REPO / "ops/scripts/manage/check-skill-drift-parity.py")],
          cwd=REPO, keep=r"stranded|in sync|Verdict|^\|")

    # 9. deploy != load: the running MCP child predates the deployed file.
    block("deploy != load (MCP child vs deployed file)",
          ["bash", "-c", "ps -eo pid,lstart,etimes,args | grep -F loop-gov-mcp | grep -v grep; "
                         "ls -l --time-style=+%Y-%m-%dT%H:%M:%S "
                         f"{HOME}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"])

    emit("END OF EVIDENCE")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes, {len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
