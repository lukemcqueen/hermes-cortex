#!/usr/bin/env python3
"""Capture re-runnable evidence for the daily briefing artifacts.

Usage: ./.venv-brief/bin/python capture_evidence.py 2026-10-10

Writes ~/.hermes/cron/output/verification-<date>.txt containing the raw
stdout of the canonical checker plus a listing, hashes and URL count, so a
future reviewer can re-execute and confirm without trusting a note.
"""
import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

OUT = os.path.expanduser("~/.hermes/cron/output")
CHECKER = os.path.expanduser(
    "~/hermes-cortex/ops/scripts/sustainability/verify_briefing.py")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main(date_str):
    base = os.path.join(OUT, f"sustainability-briefing-{date_str}")
    lines = []
    lines.append(f"=== evidence: sustainability briefing {date_str} ===")
    lines.append(f"generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    lines.append(f"--- command: {sys.executable} {CHECKER} {date_str}")
    proc = subprocess.run([sys.executable, CHECKER, date_str],
                          capture_output=True, text=True)
    lines.append(proc.stdout.rstrip())
    if proc.stderr.strip():
        lines.append("--- stderr ---")
        lines.append(proc.stderr.rstrip())
    lines.append(f"checker_exit={proc.returncode}")
    lines.append("")

    lines.append("--- artifact listing + sha256")
    for ext in (".md", ".docx", ".pdf"):
        p = base + ext
        if os.path.exists(p):
            lines.append(f"{os.path.getsize(p):>9}  {sha256(p)}  {p}")
        else:
            lines.append(f"MISSING  {p}")
    lines.append("")

    md_path = base + ".md"
    if os.path.exists(md_path):
        with open(md_path, encoding="utf-8") as fh:
            text = fh.read()
        urls = set(re.findall(r"https?://[^\s)]+", text))
        src_lines = re.findall(r"^Source: https?://\S+$", text, re.M)
        lines.append(f"--- distinct source URLs in md: {len(urls)}")
        lines.append(f"--- Source: lines: {len(src_lines)}")
        lines.append(f"--- word count: {len(text.split())}")
    lines.append("")

    lines.append("--- pdf text extraction spot-check (first 6 lines)")
    try:
        pt = subprocess.run(["pdftotext", base + ".pdf", "-"],
                            capture_output=True, text=True, timeout=60)
        lines.extend(pt.stdout.splitlines()[:6])
    except Exception as exc:  # noqa: BLE001
        lines.append(f"pdftotext unavailable: {exc}")

    dest = os.path.join(OUT, f"verification-{date_str}.txt")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {dest}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-10"))
