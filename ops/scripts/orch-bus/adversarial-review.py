#!/usr/bin/env python3
"""Independent adversarial review — assemble and run the reviewer prompt.

Story M6.3/M6.4/M6.5. This script runs ORCHESTRATOR-SIDE (the worker cannot
invoke it — no cronjob tool). It:

1. Reads the FIXED reviewer prompt from docs/templates/ (committed,
   orchestrator-only — never from worker-authored input).
2. Appends the reviewed material below the marker (as DATA).
3. --dry-run: emits the assembled prompt without calling a model (this is the
   test surface; the model call itself is exercised by the orchestrator cron
   with the real provider).
4. --sweep (cron mode): lists completed cycles with no review yet from the
   loop-governance DB, reviews each, records verdicts. Silent when the queue
   is empty (watchdog pattern).

Independence properties asserted here:
- The prompt source is the committed template, not worker text.
- The reviewed material is appended BELOW the untrusted-data marker.
- Empty reviewed material is refused (nothing to review = no review).
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

# This script lives 3 levels below the repo root (ops/scripts/orch-bus/) —
# prefer git toplevel, fall back to the counted walk-up (the classic
# walk-up-depth bug: parents[2] from ops/scripts/orch-bus is ops/, not repo).
_SCRIPT_DIR = Path(__file__).resolve().parent
try:
    REPO = Path(
        subprocess.check_output(
            ["git", "-C", str(_SCRIPT_DIR), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    )
except Exception:  # noqa: BLE001 — git unavailable; fall back to walk-up
    REPO = _SCRIPT_DIR.parents[2]
TEMPLATE = REPO / "docs" / "templates" / "adversarial-reviewer-prompt.md"
# Deployed hosts have no git clone — the template is deployed alongside this
# script by cortex-update.sh. Prefer the deployed copy when present (it is the
# version the deploy put there); fall back to the repo copy when running from
# a source checkout (dev/test).
_DEPLOYED_TEMPLATE = _SCRIPT_DIR.parent / "templates" / "adversarial-reviewer-prompt.md"
if _DEPLOYED_TEMPLATE.is_file():
    TEMPLATE = _DEPLOYED_TEMPLATE
MARKER = "=== REVIEWED MATERIAL ==="
DEFAULT_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"


def assemble_prompt(material: str) -> str:
    template = TEMPLATE.read_text()
    if MARKER not in template:
        raise SystemExit(
            f"Error: template {TEMPLATE} is missing the {MARKER!r} marker"
        )
    # Material is appended strictly below the marker — it can never displace
    # or rewrite the instructions above it (Seam A guard).
    return f"{template}\n{material}\n"


def _pending_cycles(db_path: Path, limit: int) -> list[dict]:
    """Completed cycles (decision != PENDING) with no adversarial_reviews row.

    Worker-authored material for each cycle = its outcome_note (the cycle's
    own claim about what was done). This is exactly the self-report the
    reviewer is here to challenge.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # First-run graceful: create the sink if absent (idempotent).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS adversarial_reviews ("
            " review_id TEXT PRIMARY KEY,"
            " cycle_id INTEGER NOT NULL UNIQUE,"
            " reviewer_id TEXT NOT NULL,"
            " reviewer_model TEXT NOT NULL,"
            " verdict TEXT NOT NULL,"
            " findings_json TEXT NOT NULL,"
            " summary TEXT,"
            " ts TEXT NOT NULL)"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT c.id, c.task_id, c.outcome_note, c.completeness,"
            " c.quality, c.progress"
            " FROM loop_cycles c"
            " LEFT JOIN adversarial_reviews r ON r.cycle_id = c.id"
            " WHERE r.cycle_id IS NULL AND c.decision != 'PENDING'"
            " AND c.id IS NOT NULL"
            " ORDER BY c.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _material_for(row: dict) -> str:
    """Render a cycle as reviewer-visible material (its self-report only)."""
    return (
        f"Cycle #{row['id']} (task: {row['task_id']})\n"
        f"Worker's own scores: completeness={row['completeness']}"
        f" quality={row['quality']} progress={row['progress']}\n"
        f"Worker's note (self-report — the thing being reviewed):\n"
        f"{row['outcome_note'] or '(no note)'}\n"
    )


def _call_model(prompt: str) -> str:
    model = os.environ.get("ADVERSARIAL_REVIEWER_MODEL",
                           "deepseek/deepseek-v4-pro")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        # Cron runs may not inherit the shell env — source the Hermes deploy
        # env the same way other fleet scripts do (never print the value).
        hermes_env = Path(os.environ.get("HERMES_HOME",
                                         str(Path.home() / ".hermes"))) / ".env"
        if hermes_env.exists():
            for line in hermes_env.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        raise SystemExit(
            "Error: OPENROUTER_API_KEY not set (env or ~/.hermes/.env) — "
            "cannot run the review"
        )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _extract_reviewer_json(text: str) -> tuple[str, str]:
    """Extract (findings_json, verdict) from the reviewer's reply.

    The reviewer is instructed to emit a JSON object
    {cycle_id, verdict, findings[], summary} — but models wrap JSON in prose
    or fences. Find the outermost {...}, parse it, and pull the fields; if
    parsing fails, record an empty findings array with verdict FINDINGS and
    let the summary carry the raw text (never silently drop a review).
    """
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            findings = obj.get("findings", [])
            if not isinstance(findings, list):
                findings = []
            verdict = obj.get("verdict", "FINDINGS" if findings else "CLEAN")
            return json.dumps(findings), str(verdict)
        except json.JSONDecodeError:
            pass
    # Unparseable reviewer output: never dropped, never trusted as CLEAN.
    return "[]", "FINDINGS"


def _record(db_path: Path, cycle_id: int, reviewer_id: str, model: str,
            text: str) -> int:
    """Insert the review verdict directly into the adversarial_reviews table."""
    findings_json, verdict = _extract_reviewer_json(text)
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS adversarial_reviews ("
            " review_id TEXT PRIMARY KEY,"
            " cycle_id INTEGER NOT NULL UNIQUE,"
            " reviewer_id TEXT NOT NULL,"
            " reviewer_model TEXT NOT NULL,"
            " verdict TEXT NOT NULL,"
            " findings_json TEXT NOT NULL,"
            " summary TEXT,"
            " ts TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO adversarial_reviews"
            " (review_id, cycle_id, reviewer_id, reviewer_model,"
            "  verdict, findings_json, summary, ts)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                cycle_id,
                reviewer_id,
                model,
                verdict,
                findings_json,
                text[:2000],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            print(f"  cycle #{cycle_id}: already reviewed (UNIQUE constraint)",
                  file=sys.stderr)
        else:
            print(f"  cycle #{cycle_id}: DB error: {e}", file=sys.stderr)
        return 3
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cycle-id", type=int, default=None,
                   help="review one specific cycle (with --material)")
    p.add_argument("--material", default=None,
                   help="the reviewed output (worker-authored, untrusted)")
    p.add_argument("--db", default=str(DEFAULT_DB),
                   help="loop-governance DB path")
    p.add_argument("--reviewer-id", default=None,
                   help="distinct reviewer session id (default: generated)")
    p.add_argument("--limit", type=int, default=5,
                   help="max cycles per sweep (default 5)")
    p.add_argument("--review", action="store_true",
                   help="call the model and record the verdict")
    p.add_argument("--sweep", action="store_true",
                   help="review every completed cycle that has no review yet")
    p.add_argument("--dry-run", action="store_true",
                   help="assemble and print the prompt; do not call a model")
    args = p.parse_args()

    if not args.sweep and args.cycle_id is None and args.material is None:
        # Cron mode: install-orch-crons.sh create_cron() registers this script
        # with NO argument mechanism, so the orchestrator cron invokes it bare.
        # A bare invocation IS the sweep (docstring: --sweep is "cron mode");
        # erroring here 3-strike-pauses the cron (2026-09-24 incident).
        args.sweep = True

    if args.sweep:
        db_path = Path(args.db).expanduser()
        if not db_path.exists():
            print(f"silent: no loop-governance DB at {db_path}")
            return 0
        pending = _pending_cycles(db_path, args.limit)
        if not pending:
            print("silent: no unreviewed completed cycles")
            return 0
        reviewer_id = args.reviewer_id or f"adv-review-{uuid.uuid4().hex[:8]}"
        model = os.environ.get("ADVERSARIAL_REVIEWER_MODEL",
                               "deepseek/deepseek-v4-pro")
        print(f"sweep: {len(pending)} cycle(s) to review (reviewer {reviewer_id})")
        failed = 0
        for row in pending:
            try:
                prompt = assemble_prompt(_material_for(row))
                text = _call_model(prompt)
                rc = _record(db_path, row["id"], reviewer_id, model, text)
                if rc != 0:
                    failed += 1
                print(f"  cycle #{row['id']}: recorded (rc={rc})")
            except SystemExit as e:
                print(f"  cycle #{row['id']}: {e}", file=sys.stderr)
                failed += 1
        return 1 if failed else 0

    # Single-cycle mode
    if args.cycle_id is None or args.material is None:
        p.error("single-cycle mode requires --cycle-id and --material "
                "(or use --sweep)")
    if not args.material.strip():
        print("Error: empty --material — nothing to review", file=sys.stderr)
        return 2
    if args.review and not args.reviewer_id:
        print("Error: --review requires --reviewer-id", file=sys.stderr)
        return 2

    prompt = assemble_prompt(args.material)

    if args.dry_run:
        print(prompt)
        return 0

    if not args.review:
        p.error("nothing to do: pass --dry-run, --review, or --sweep")

    model = os.environ.get("ADVERSARIAL_REVIEWER_MODEL",
                           "deepseek/deepseek-v4-pro")
    text = _call_model(prompt)
    reviewer_id = args.reviewer_id or f"adv-review-{uuid.uuid4().hex[:8]}"
    return _record(Path(args.db).expanduser(), args.cycle_id, reviewer_id,
                   model, text)


if __name__ == "__main__":
    sys.exit(main())
