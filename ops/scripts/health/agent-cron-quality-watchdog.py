#!/usr/bin/env python3
"""
Cron Output Quality Watchdog — no_agent script. agent-cron-quality-watchdog.py

Runs every 10 minutes. Checks the most recent delivery output from
every LLM-driven (no_agent=False) cron job for quality issues:

  - QUALITY_G_BLOCKED token -> cron agent self-blocked
  - Response oversized (> 12000 chars) -> possible runaway
  - Response empty when an output file exists -> silent failure
  - High ratio of non-ASCII / control chars -> possible gibberish
  - Repetitive content -> gibberish
  - Session-guard skip contract: guard said ACTIVE but the reply was not
    the mandated skip token (2026-08-04 regression: agent-inbox-workday
    delivered "participacao" and cortex-bus-workday delivered "todavia |
    participacao | postfix" instead of the skip token after a model stall)

Output directories are keyed by JOB ID (not name) — resolved via jobs.json.
Checks run against the ## Response section only (not the embedded prompt/skill).

SILENT when everything is clean (classic watchdog pattern).
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────────────
CRON_OUTPUT_DIR = Path(os.path.expanduser("~/.hermes/cron/output"))
CRON_JOBS_FILE = Path(os.path.expanduser("~/.hermes/cron/jobs.json"))
QUALITY_BLOCK_TOKEN = "QUALITY_G_BLOCKED"
SILENT_TOKEN = "[SILENT]"
MAX_CHARS = 12000  # local-agent-daily-news-brief targets ~7600 chars
MIN_REPORT_CHARS = 100  # below this (non-MEDIA, non-skip) = token garbage
SUSPICIOUS_UNICODE_RATIO = 0.30  # if >30% of chars are non-ASCII/control
ACTIVE_MARKER = "ACTIVE ("  # session-active-guard output when interactive
SKIP_TOKEN_MARKERS = ("skipped", "interactive session")  # normalised skip reply

# Known-bad fallback models (2026-08-11): when the primary provider fails,
# the fallback chain bottomed out in qwen2.5-coder:3b (custom:ollama-local),
# which emits token garbage for agentic tool-use loops while the scheduler
# records last_status: ok (a response WAS emitted — it was just garbage).
# First seen 2026-08-09 on the bible-reading cron; recurred 2026-08-11 on
# agent-fixer-workday (49 chars of '\\\\\nin 0.' noise) and orch-backlog-driver
# (80 chars of 'ly, what really' noise). A green status is NOT evidence of
# correct output — the guard is to never let the chain end in a model that
# cannot do agentic work. Remove the entry with `hermes fallback remove`.
KNOWN_BAD_FALLBACK_MODELS = {
    "qwen2.5-coder:3b": "emits token garbage for agentic tool-use loops (2026-08-09, 2026-08-11)",
}
FALLBACK_CONFIG_FILE = Path(os.path.expanduser("~/.hermes/config.yaml"))


# ── Helpers ─────────────────────────────────────────────────────────────────
def _get_jobs() -> list[dict]:
    """Load the cron jobs registry."""
    if not CRON_JOBS_FILE.exists():
        return []
    try:
        with open(CRON_JOBS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("jobs", [])
    except (json.JSONDecodeError, OSError):
        return []


def _find_latest_output(job_id: str) -> Optional[str]:
    """Read the most recent output file for a cron job by its JOB ID."""
    job_dir = CRON_OUTPUT_DIR / job_id
    if not job_dir.is_dir():
        return None
    latest = job_dir / "latest.md"
    if latest.exists():
        try:
            return latest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    # Fallback: newest timestamped .md file
    files = sorted(job_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in files:
        if fp.name != "latest.md":
            try:
                return fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return None


def _extract_response(content: str) -> Optional[str]:
    """Pull the text after the '## Response' marker (the LLM's actual output)."""
    marker = "## Response"
    idx = content.find(marker)
    if idx == -1:
        return None
    return content[idx + len(marker):].strip()


def _extract_script_output(content: str) -> str:
    """Pull the pre-run script output section (session guard etc.)."""
    start = content.find("## Script Output")
    if start == -1:
        return ""
    block = content[start:]
    end = block.find("## Response")
    if end != -1:
        block = block[:end]
    return block


def _is_empty_or_whitespace(text: str) -> bool:
    return not text or not text.strip()


def _is_silent_noop(response: str) -> bool:
    """True for the healthy no-op token in any JSON/quote/whitespace wrapping.

    Gisu proposal 2026-08-19: a one-off model deviation emitted the JSON-wrapped
    no-op ["SILENT"] (14 chars) which failed the literal `response == "[SILENT]"`
    match and fell through to Check 5b (short response = "token garbage").
    Normalize away wrapping whitespace/quotes before the no-op check.
    """
    normalized = re.sub(r"[\s\"']", "", response.strip())
    return normalized in ("[SILENT]", "SILENT")


def _count_suspicious_chars(text: str) -> int:
    """Count non-printable/non-ASCII characters that suggest gibberish."""
    count = 0
    for ch in text:
        cp = ord(ch)
        # Control characters (except common whitespace)
        if cp < 32 and cp not in (9, 10, 13):  # tab, newline, CR
            count += 1
        # Surrogates/unusual high codepoints
        elif 0xD800 <= cp <= 0xDFFF:
            count += 1
        # Very high unicode that usually indicates encoding corruption
        elif cp > 0x1FFFF:
            count += 1
        # Repeated replacement characters
        elif ch == "\ufffd":
            count += 1
    return count


def _is_repetitive_gibberish(text: str) -> bool:
    """Check for extremely repetitive patterns."""
    if len(text) < 50:
        return False
    for length in [5, 10, 20]:
        if len(text) >= length * 3:
            chunks = [text[i:i + length] for i in range(0, len(text), length)]
            chunk_counts = Counter(chunks)
            most_common_count = chunk_counts.most_common(1)[0][1]
            if most_common_count > len(chunks) * 0.3:
                return True
    return False


def _is_skip_reply(response: str) -> bool:
    """True when the response is the session-guard skip token (normalised)."""
    low = response.lower()
    return all(m in low for m in SKIP_TOKEN_MARKERS)


def _audit_fallback_chain() -> list[str]:
    """Flag fallback-chain entries that produce garbage instead of failing.

    A known-bad model in the chain means: when the primary provider is down,
    crons silently deliver token garbage with last_status: ok instead of
    failing loudly. Checked every tick so a regression is caught before the
    next outage, not after the next delivery.
    """
    try:
        import yaml
    except ImportError:
        return []
    if not FALLBACK_CONFIG_FILE.exists():
        return []
    try:
        with open(FALLBACK_CONFIG_FILE, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return []
    chain = cfg.get("fallback_providers") or []
    if isinstance(chain, dict):  # legacy single-dict format
        chain = [chain]
    issues = []
    for entry in chain:
        if not isinstance(entry, dict):
            continue
        model = entry.get("model", "")
        provider = entry.get("provider", "")
        if model in KNOWN_BAD_FALLBACK_MODELS:
            issues.append(
                f"\U0001f534 fallback chain: {model} (via {provider}) — "
                f"{KNOWN_BAD_FALLBACK_MODELS[model]}; crons will deliver "
                f"garbage instead of failing when the primary is down. "
                f"Remove with: hermes fallback remove"
            )
    return issues


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    issues: list[str] = []

    # Check 0: fallback chain audit — catches the CAUSE (a known-garbage
    # fallback model) before the next outage produces the symptom.
    issues.extend(_audit_fallback_chain())

    jobs = _get_jobs()

    # Monitor every LLM-driven job (no_agent=False) that has an output file.
    llm_jobs = [j for j in jobs if j.get("no_agent") in (None, False)]

    for job in llm_jobs:
        job_id = job.get("id")
        name = job.get("name") or job_id
        if not job_id:
            continue

        content = _find_latest_output(job_id)
        if content is None:
            continue

        response = _extract_response(content)
        if response is None:
            continue  # no ## Response section (hung/interrupted run) — nothing to evaluate

        # Check 1: self-block token
        if QUALITY_BLOCK_TOKEN in response:
            issues.append(f"\U0001f534 {name}: AGENT SELF-BLOCKED (QUALITY_G_BLOCKED token found)")
            continue

        # [SILENT] is the healthy no-op signal (also JSON/quote-wrapped variants,
        # gisu proposal 2026-08-19 — one-off model deviation emitted ["SILENT"])
        if _is_silent_noop(response):
            continue

        # Check 2: empty response
        if _is_empty_or_whitespace(response):
            issues.append(f"\U0001f7e1 {name}: empty response (possible silent failure)")
            continue

        # Check 3: oversized response
        if len(response) > MAX_CHARS:
            issues.append(
                f"\U0001f7e0 {name}: oversized response ({len(response)} chars, "
                f"limit {MAX_CHARS}) \u2014 possible runaway"
            )

        # Check 4: gibberish unicode
        total_chars = len(response)
        suspicious = _count_suspicious_chars(response)
        if total_chars > 0 and (suspicious / total_chars) > SUSPICIOUS_UNICODE_RATIO:
            issues.append(
                f"\U0001f534 {name}: high ratio of suspicious chars "
                f"({suspicious}/{total_chars} = {suspicious / total_chars:.0%}) "
                f"\u2014 possible encoding corruption"
            )

        # Check 5: repetitive gibberish
        if _is_repetitive_gibberish(response):
            issues.append(f"\U0001f534 {name}: extremely repetitive content \u2014 possible gibberish")

        # Check 5b: suspiciously short ASCII response (2026-08-10)
        # deepseek-v4-flash once returned 40 chars of token garbage
        # ("9oursucceeded 60 95 in 1 2") as a "successful" weekly eval.
        # Legit short forms: [SILENT] (handled above), a MEDIA: file
        # delivery, or the session-guard skip reply (handled below).
        # Anything else under MIN_REPORT_CHARS is incoherent churn.
        if not response.startswith("MEDIA:"):
            if len(response) < MIN_REPORT_CHARS:
                issues.append(
                    f"\U0001f7e0 {name}: suspiciously short response "
                    f"({len(response)} chars < {MIN_REPORT_CHARS}) "
                    f"{response[:60]!r} \u2014 possible token garbage"
                )

        # Check 6: session-guard skip contract
        # Guard said ACTIVE -> the ONLY valid reply is the skip token. Anything
        # else (stray words, fabricated summaries) means the model glitched.
        script_out = _extract_script_output(content)
        if ACTIVE_MARKER in script_out and not _is_skip_reply(response):
            issues.append(
                f"\U0001f7e0 {name}: session guard said ACTIVE but reply was "
                f"{response[:60]!r} \u2014 expected the skip token"
            )

    if not issues:
        # Silent — no news is good news
        sys.exit(0)

    # Build a compact report
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    print(f"## Cron Quality Watchdog \u2014 {now}")
    print()
    print(f"{len(issues)} issue(s) detected:")
    print()
    for issue in issues:
        print(f"- {issue}")
    print()
    print("Check ~/.hermes/cron/output/<job-id>/ for full output.")


if __name__ == "__main__":
    main()
