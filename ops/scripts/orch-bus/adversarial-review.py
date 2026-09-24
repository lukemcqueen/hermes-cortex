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

Independence properties asserted here:
- The prompt source is the committed template, not worker text.
- The reviewed material is appended BELOW the untrusted-data marker.
- Empty reviewed material is refused (nothing to review = no review).
"""

import argparse
import subprocess
import sys
from pathlib import Path

# This script lives 3 levels below the repo root (ops/scripts/orch-bus/) —
# parents[3], not parents[2] (the classic walk-up-depth bug). Prefer git
# toplevel, fall back to the counted walk-up.
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
MARKER = "=== REVIEWED MATERIAL ==="


def assemble_prompt(material: str) -> str:
    template = TEMPLATE.read_text()
    if MARKER not in template:
        raise SystemExit(
            f"Error: template {TEMPLATE} is missing the {MARKER!r} marker"
        )
    # Material is appended strictly below the marker — it can never displace
    # or rewrite the instructions above it (Seam A guard).
    return f"{template}\n{material}\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cycle-id", type=int, required=True)
    p.add_argument("--material", required=True,
                   help="the reviewed output (worker-authored, untrusted)")
    p.add_argument("--db", default=None,
                   help="loop-governance DB path (for --review)")
    p.add_argument("--reviewer-id", default=None,
                   help="distinct reviewer session id (for --review)")
    p.add_argument("--review", action="store_true",
                   help="call the model and record the verdict")
    p.add_argument("--dry-run", action="store_true",
                   help="assemble and print the prompt; do not call a model")
    args = p.parse_args()

    if not args.material.strip():
        print("Error: empty --material — nothing to review", file=sys.stderr)
        return 2
    if args.review and not (args.db and args.reviewer_id):
        print("Error: --review requires --db and --reviewer-id", file=sys.stderr)
        return 2

    prompt = assemble_prompt(args.material)

    if args.dry_run:
        print(prompt)
        return 0

    if not args.review:
        p.error("nothing to do: pass --dry-run or --review")

    # The model call is made by the orchestrator cron (LLM_CRON_PROVIDER,
    # deepseek-v4-pro per the operator decision). Import lazily so --dry-run
    # works without provider credentials.
    import json
    import os
    import urllib.request

    model = os.environ.get("ADVERSARIAL_REVIEWER_MODEL", "deepseek/deepseek-v4-pro")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set — cannot run the review",
              file=sys.stderr)
        return 3

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
    text = data["choices"][0]["message"]["content"]

    # Extract the findings JSON from the reviewer's reply (it is instructed to
    # emit JSON; anything else is recorded as an info finding).
    start = text.find("{")
    end = text.rfind("}")
    findings_json = text[start:end + 1] if start != -1 and end > start else "[]"
    verdict = "FINDINGS" if '"verdict": "FINDINGS"' in text else "CLEAN"

    record = Path(__file__).resolve().parents[1] / "manage" / "record-review.py"
    import subprocess
    rc = subprocess.run([
        sys.executable, str(record),
        "--db", args.db,
        "--cycle-id", str(args.cycle_id),
        "--reviewer-id", args.reviewer_id,
        "--reviewer-model", model,
        "--verdict", verdict,
        "--findings-json", findings_json,
        "--summary", text[:2000],
    ]).returncode
    return rc


if __name__ == "__main__":
    sys.exit(main())
