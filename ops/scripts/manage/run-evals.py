#!/usr/bin/env python3
"""
Eval Harness — run evaluation suites against live fleet invariants (F-008).

REAL deterministic grading only. No simulated passes: every `deterministic`
grader name in an eval YAML must exist in the GRADERS registry below, and
every grader executes real checks against the live system (bus API, task DB,
doctor JSON, skills manifest). Unknown grader names fail loudly — never
silently skipped.

STANDALONE MODE (cron / shell):
    python3 run-evals.py --suite regression --standalone
    python3 run-evals.py --eval regression-golden --standalone

AGENT MODE (inside Hermes session):
    python3 run-evals.py --suite regression

Exit codes: 0 = all tasks passed, 1 = any task failed.
The no_agent cron wrapper (orch-daily-regression-gate.sh) suppresses stdout
on success and emits the report + exit 1 on failure (watchdog pattern).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:
    yaml = None  # checked in _load_yaml — fail loudly, never simulate

# ── Configuration ────────────────────────────────────────────────

HOME = Path.home()
CORTEX_HOME = HOME / ".hermes-cortex"
EVALS_DIR = CORTEX_HOME / "evals"
TRACES_DIR = EVALS_DIR / "traces"
REPORTS_DIR = EVALS_DIR / "reports"
EVALS_REPO_DIR = HOME / "hermes-cortex" / "evals"
SCRIPTS_DIR = CORTEX_HOME / "scripts"
SKILLS_MANIFEST = CORTEX_HOME / "skills.yaml"
DOCTOR = SCRIPTS_DIR / "cortex-doctor.py"
TASK_DB = SCRIPTS_DIR / "task-db.py"

TRACES_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    """Load a YAML file. Fail loudly when PyYAML is missing."""
    if yaml is None:
        raise RuntimeError("PyYAML is not installed — cannot parse eval definitions")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    """Run a command, return (rc, combined output). Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s: {' '.join(cmd[:2])}..."
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"


def _task_db_identity() -> tuple[str, str]:
    """Resolve the local task-DB reader role + creator name.

    Mirrors task-db.py's canonical profile resolution (HERMES_PROFILE →
    AGENT_NAME → agent.env/.env, never hostname) so the probe delete connects
    as the SAME role that created the probe. Each host provisions only its own
    mycortex_reader_<profile> role; hardcoding another agent's role (esther)
    broke the gate on the moses host (2026-08-09).
    """
    def _env_or_file() -> str:
        val = os.environ.get("AGENT_NAME", "").strip()
        if val and val != "unknown":
            return val
        for _p in (Path.home() / ".hermes-cortex" / "agent.env",
                   Path.home() / "hermes-cortex" / ".env"):
            try:
                if _p.is_file():
                    for _l in _p.read_text().splitlines():
                        _l = _l.strip()
                        if _l.startswith("AGENT_NAME="):
                            _v = _l.split("=", 1)[1].strip().strip("\"'")
                            if _v and _v != "unknown":
                                return _v
            except OSError:
                continue
        return ""
    profile = (os.environ.get("HERMES_PROFILE")
               or _env_or_file()
               or sys.exit("❌ AGENT_NAME not configured — set AGENT_NAME= in "
                           "~/.hermes-cortex/agent.env / ~/hermes-cortex/.env "
                           "or export AGENT_NAME"))
    return f"mycortex_reader_{profile}", profile


# ── Grader registry ──────────────────────────────────────────────
# name -> callable() returning (passed: bool, detail: str)

GRADERS: dict[str, Callable[[], tuple[bool, str]]] = {}


def grader(name: str) -> Callable:
    def deco(fn: Callable[[], tuple[bool, str]]) -> Callable:
        GRADERS[name] = fn
        return fn
    return deco


# ── Golden graders (suite v1: bus, task lifecycle, exec, doctor, skills) ──

@grader("bus_round_trip")
def _bus_round_trip() -> tuple[bool, str]:
    """Send a probe message to inbox_esther, read it back (vt-hidden), archive it.

    Uses the CANONICAL lib.cortex_bus client (Bearer→Basic auth fallback,
    retries, fallback URL — nginx validates Basic auth and ignores Bearer
    through the proxy). Tests the ACTIVE bus path the agent's own crons use.
    The vt=600 peek hides the message from the 5-min message-handler poll and
    the audit watchdog (DLQ/stuck >5min only), so the probe is invisible to
    consumers and leaves zero residue.
    """
    # Resolve the deployed scripts dir so `lib.cortex_bus` imports in both
    # layouts: deployed (~/.hermes-cortex/scripts/) and in-repo (ops/scripts/).
    scripts_dir = SCRIPTS_DIR if SCRIPTS_DIR.is_dir() else HOME / "hermes-cortex" / "ops" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from lib.cortex_bus import bus_archive, bus_read, bus_send  # noqa: PLC0415
    except ImportError as e:
        return False, f"cannot import lib.cortex_bus: {e}"

    queue = "inbox_esther"
    correlation_id = f"regression-gate-{uuid.uuid4().hex[:12]}"
    probe = {
        # Subject PING = a known silent-noise subject the message-handler
        # archives without alerting — a probe raced by the 5-min poll is
        # silently removed, never processed as a command.
        "subject": "PING",
        "body": {"regression_gate": True, "correlation_id": correlation_id},
        "correlation_id": correlation_id,
    }

    # 1. Send
    sent = bus_send(queue, probe)
    if not sent or not sent.get("msg_id"):
        return False, f"send failed: {json.dumps(sent)[:160] if sent else 'no response'}"
    sent_id = sent["msg_id"]

    # 2. Read back (vt=600 — hidden, not consumed)
    msg = bus_read(queue, vt=600)
    if not msg or not msg.get("msg_id"):
        return False, "read failed: no message returned"
    if msg.get("correlation_id") != correlation_id:
        return False, (f"read returned msg {str(msg.get('msg_id'))[:8]} but "
                       f"correlation mismatch (expected {correlation_id[:8]}…)")

    # 3. Archive (removes the hidden probe — zero residue)
    if not bus_archive(queue, msg["msg_id"]):
        return False, "archive failed — probe left hidden until vt expiry"

    return True, (f"send→read→archive OK (msg {str(sent_id)[:8]}, "
                  f"correlation {correlation_id[:8]}…) via lib.cortex_bus")


@grader("task_lifecycle")
def _task_lifecycle() -> tuple[bool, str]:
    """Task DB add → list → update → delete round-trip via task-db.py.

    Creates a probe row tagged regression-gate, verifies it lists, updates it
    to completed, then deletes it directly (reader role has DELETE). Zero
    residue — the probe must never survive the gate run.
    """
    if not TASK_DB.exists():
        return False, f"task-db.py not found at {TASK_DB}"

    probe_content = f"REGRESSION-GATE-PROBE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    probe_id: str | None = None

    def _find_probe_id(out: str) -> str | None:
        m = re.search(rf"([0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}).*{re.escape(probe_content)}", out)
        return m.group(1) if m else None

    try:
        # 1. Add
        rc, out = _run(["python3", str(TASK_DB), "add", probe_content,
                        "--tag", "regression-gate", "--source", "manual"])
        if rc != 0:
            return False, f"add failed (rc={rc}): {out.strip()[-200:]}"

        # 2. List — confirm the probe is visible
        rc, out = _run(["python3", str(TASK_DB), "list", "--tag", "regression-gate"])
        if rc != 0:
            return False, f"list failed (rc={rc}): {out.strip()[-200:]}"
        probe_id = _find_probe_id(out)
        if not probe_id:
            return False, "probe task not found in list output"

        # 3. Start → complete (v005 transition matrix: pending → completed
        #    is illegal — must start first)
        rc, out = _run(["python3", str(TASK_DB), "update", probe_id, "--status", "in_progress"])
        if rc != 0:
            return False, f"start update failed (rc={rc}): {out.strip()[-200:]}"
        rc, out = _run(["python3", str(TASK_DB), "update", probe_id, "--status", "completed"])
        if rc != 0:
            return False, f"update failed (rc={rc}): {out.strip()[-200:]}"

        # 4. Delete the probe row directly (reader role has DELETE per v001).
        #    Connect as the LOCAL profile reader role — the probe was created
        #    as <local profile> by task-db.py (resolve_profile chain), and each
        #    host only provisions its own mycortex_reader_<profile> role. The
        #    previously hardcoded mycortex_reader_esther did not exist on the
        #    moses host → gate failed with 'role does not exist' (2026-08-09).
        probe_role, probe_creator = _task_db_identity()
        delete_sql = (f"DELETE FROM tasks.tasks WHERE id = '{probe_id}' "
                      f"AND created_by = '{probe_creator}';")
        rc, out = _run(["docker", "exec", "-i", "mycortex-postgres", "psql",
                        "-U", probe_role, "-d", "mycortex",
                        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", delete_sql])
        if rc != 0:
            return False, f"probe delete failed (rc={rc}): {out.strip()[-200:]}"

        return True, f"add→list→update→delete OK (probe {probe_id[:8]}… removed)"
    finally:
        # Safety net: if anything above failed after add, remove the probe now.
        if probe_id:
            probe_role, _ = _task_db_identity()
            _run(["docker", "exec", "-i", "mycortex-postgres", "psql",
                  "-U", probe_role, "-d", "mycortex",
                  "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c",
                  f"DELETE FROM tasks.tasks WHERE id = '{probe_id}';"])


@grader("exec_round_trip")
def _exec_round_trip() -> tuple[bool, str]:
    """Subprocess exec returns expected output — proves the exec path works."""
    rc, out = _run(["python3", "-c", "print('EXEC-OK')"], timeout=30)
    if rc != 0:
        return False, f"python3 -c failed (rc={rc}): {out.strip()[-200:]}"
    if "EXEC-OK" not in out:
        return False, f"expected EXEC-OK in output, got: {out.strip()[-200:]}"
    return True, "python3 exec round-trip OK"


@grader("doctor_clean")
def _doctor_clean() -> tuple[bool, str]:
    """Cortex doctor reports zero failures (warns tolerated)."""
    if not DOCTOR.exists():
        return False, f"cortex-doctor.py not found at {DOCTOR}"
    rc, out = _run(["python3", str(DOCTOR), "--json"], timeout=120)
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        return False, f"doctor JSON parse failed (rc={rc}): {out.strip()[-200:]}"
    summary = report.get("summary", {})
    fails = summary.get("fail", -1)
    warns = summary.get("warn", 0)
    if fails is None or fails < 0:
        return False, f"doctor summary missing 'fail': {json.dumps(summary)[:160]}"
    if fails > 0:
        return False, f"doctor reports {fails} failure(s), {warns} warn(s) — gate blocked"
    return True, f"doctor clean (pass {summary.get('pass', 0)}, warn {warns}, fail 0)"


@grader("core_skills")
def _core_skills() -> tuple[bool, str]:
    """Every always-section skill in skills.yaml resolves to a loadable SKILL.md."""
    if not SKILLS_MANIFEST.exists():
        return False, f"skills.yaml not found at {SKILLS_MANIFEST}"
    manifest = _load_yaml(SKILLS_MANIFEST)
    always = manifest.get("always", [])
    if not always:
        return False, "skills.yaml 'always' section is empty"

    missing: list[str] = []
    for entry in always:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            continue
        matches = list((HOME / ".hermes" / "skills").rglob(f"{name}/SKILL.md"))
        if not matches:
            missing.append(f"{name} (no SKILL.md)")
            continue
        # Validate frontmatter parses + name matches
        try:
            text = matches[0].read_text()
            m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if not m:
                missing.append(f"{name} (no frontmatter)")
                continue
            fm = yaml.safe_load(m.group(1)) if yaml else {}
            if not isinstance(fm, dict) or fm.get("name") != name:
                missing.append(f"{name} (frontmatter name mismatch: {fm.get('name')})")
        except Exception as e:  # noqa: BLE001 — any failure = skill broken; record, don't abort
            missing.append(f"{name} ({type(e).__name__})")

    if missing:
        return False, "broken always-skills: " + "; ".join(missing)
    return True, f"all {len(always)} always-skills present and loadable"


# ── Suite / task execution ───────────────────────────────────────

def load_eval_definition(eval_name: str) -> dict:
    """Load eval definition from repo or deployed evals/ dir."""
    for base in (EVALS_REPO_DIR, EVALS_DIR):
        p = base / f"{eval_name}.yaml"
        if p.exists():
            return _load_yaml(p)
    raise FileNotFoundError(f"Eval definition not found: {eval_name}.yaml "
                            f"(looked in {EVALS_REPO_DIR} and {EVALS_DIR})")


def run_task(task: dict, capture_traces: bool = False) -> dict:
    """Run a single eval task: execute every deterministic grader for real."""
    task_id = task.get("id", "unknown")
    grading = task.get("grading", {})
    grader_names = grading.get("deterministic", [])
    llm_rubric = grading.get("llm_rubric")

    scores: dict[str, dict] = {}
    for gname in grader_names:
        fn = GRADERS.get(gname)
        if fn is None:
            scores[gname] = {"passed": False,
                             "detail": f"UNKNOWN GRADER '{gname}' — fail-closed, no silent skip"}
            continue
        try:
            passed, detail = fn()
        except Exception as e:  # noqa: BLE001 — grader crash = task failure
            passed, detail = False, f"grader raised {type(e).__name__}: {e}"
        scores[gname] = {"passed": passed, "detail": detail}

    det_passed = all(s["passed"] for s in scores.values()) if scores else False
    # LLM rubric: not graded in this deterministic-only harness — recorded, not scored.
    llm_note = ""
    if llm_rubric:
        llm_note = " (llm_rubric present but not graded — deterministic-only harness)"

    result = {
        "task_id": task_id,
        "description": task.get("description", ""),
        "deterministic_scores": scores,
        "llm_rubric_present": bool(llm_rubric),
        "passed": det_passed,
        "detail": "; ".join(f"{k}: {v['detail']}" for k, v in scores.items()) + llm_note,
        "error": None,
    }

    if capture_traces:
        trace_path = TRACES_DIR / f"eval-{task_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        trace_path.write_text(json.dumps(result, indent=2))
        result["trace_path"] = str(trace_path)

    return result


def run_eval_suite(eval_def: dict, capture_traces: bool = False) -> dict:
    """Run all tasks in an eval definition, aggregate results."""
    results = [run_task(t, capture_traces) for t in eval_def.get("tasks", [])]
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    return {
        "eval_name": eval_def.get("name", "unknown"),
        "description": eval_def.get("description", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tasks": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0.0,
        "results": results,
    }


def print_summary(summary: dict) -> None:
    """Human-readable report."""
    print("=" * 60)
    print(f"Eval Results: {summary['eval_name']}")
    print(f"{summary.get('description', '')}")
    print("=" * 60)
    print(f"Overall: {summary['pass_rate'] * 100:.0f}% pass "
          f"({summary['passed']}/{summary['total_tasks']} tasks)\n")
    for r in summary["results"]:
        mark = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"  {mark}: {r['task_id']}")
        print(f"      {r['detail']}")
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run eval suites against live fleet invariants")
    parser.add_argument("--eval", type=str, help="Name of eval to run")
    parser.add_argument("--suite", type=str, help="Name of eval suite to run")
    parser.add_argument("--standalone", action="store_true",
                        help="Standalone mode (cron/shell — no Hermes session needed)")
    parser.add_argument("--holdout", action="store_true", help="Accepted for CLI compat (no holdout split in golden suite)")
    parser.add_argument("--capture-traces", action="store_true", help="Write per-task trace JSON")
    args = parser.parse_args()

    if not args.eval and not args.suite:
        print("Error: Must specify --eval or --suite")
        parser.print_help()
        return 1

    try:
        if args.suite:
            suite_path = EVALS_REPO_DIR / "suites" / f"{args.suite}.yaml"
            if not suite_path.exists():
                print(f"Error: Suite not found: {args.suite} ({suite_path})")
                return 1
            suite_def = _load_yaml(suite_path)
            eval_names = suite_def.get("evals", [])
            if not eval_names:
                print(f"Error: Suite {args.suite} has no evals list")
                return 1
        else:
            eval_names = [args.eval]

        any_fail = False
        for eval_name in eval_names:
            eval_def = load_eval_definition(eval_name)
            summary = run_eval_suite(eval_def, capture_traces=args.capture_traces)
            print_summary(summary)
            # Persist report for trend tracking
            report_path = REPORTS_DIR / f"eval-{summary['eval_name']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            report_path.write_text(json.dumps(summary, indent=2))
            if summary["failed"] > 0:
                any_fail = True

        return 1 if any_fail else 0

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error running evals: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
