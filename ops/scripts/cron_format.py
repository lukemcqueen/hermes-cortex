#!/usr/bin/env python3
"""
cron_format.py — Shared output formatter for the standard cron format.

Usage:
    from cron_format import CronFormat

    cf = CronFormat("service-recovery")
    cf.header("service-recovery (abc123) [2026-07-03 12:01 KST]")
    cf.phase("Issues found", "2 services recovered", [
        "nginx: restart succeeded",
        "docker: container back online",
    ])
    cf.phase("Unresolved", "0 remaining")
    cf.result("All services healthy.")
    cf.footer()
    print(cf.output())
    # or just: print(cf.build_text())

    # Shortcut for simple scripts:
    print(CronFormat.simple("service-recovery", "phase content here"))
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    from hermes_tz import format_timestamp as _fmt_ts
except ImportError:
    def _fmt_ts(fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
        return datetime.now().astimezone().strftime(fmt)


class CronFormat:
    """Build standard cron format output."""

    def __init__(self, script_name: str, cron_id: str = "JOB_ID"):
        self.script_name = script_name
        self.cron_id = cron_id
        self.parts: list[str] = []
        self._started = False

    def _timestamp(self) -> str:
        """Return configured-TZ timestamp (HERMES_TIMEZONE, else system local)."""
        return _fmt_ts("%Y-%m-%d %H:%M %Z")

    def header(self, custom: Optional[str] = None) -> "CronFormat":
        """Add header line + separator."""
        if custom:
            self.parts.append(custom)
        else:
            self.parts.append(f"{self.script_name} ({self.cron_id}) [{self._timestamp()}]")
        self.parts.append("-------------")
        self.parts.append("")
        self._started = True
        return self

    def phase(self, title: str, summary: str, bullets: Optional[list[str]] = None) -> "CronFormat":
        """Add a Phase N section."""
        n = sum(1 for p in self.parts if p.startswith("Phase ")) + 1
        line = f"Phase {n} — {title}: {summary}"
        self.parts.append(line)
        if bullets:
            for b in bullets:
                self.parts.append(f"- {b}")
        self.parts.append("")
        return self

    def result(self, verdict: str) -> "CronFormat":
        """Add Result line."""
        self.parts.append(f"Result: {verdict}")
        self.parts.append("")
        return self

    def footer(self, model: Optional[str] = None, cost: str = "$0") -> "CronFormat":
        """Add footer with cost info."""
        m = model or self.script_name
        self.parts.append(f"📊 {m} | {cost}")
        return self

    def silent(self) -> str:
        """Return [SILENT] for watchdog pattern."""
        return "[SILENT]"

    def output(self) -> str:
        """Get the built string."""
        return "\n".join(self.parts).rstrip("\n")

    def build_text(self) -> str:
        """One-shot: build and return the full output."""
        if not self._started:
            self.header()
        return self.output()

    @staticmethod
    def simple(name: str, phase1_title: str, phase1_summary: str,
               phase1_bullets: Optional[list[str]] = None,
               phase2_title: str = "", phase2_summary: str = "",
               phase2_bullets: Optional[list[str]] = None,
               phase3_title: str = "", phase3_summary: str = "",
               phase3_bullets: Optional[list[str]] = None,
               verdict: str = "Complete.",
               model: Optional[str] = None) -> str:
        """Quick builder for simple scripts."""
        cf = CronFormat(name, "JOB_ID")
        cf.header()
        cf.phase(phase1_title, phase1_summary, phase1_bullets)
        if phase2_title:
            cf.phase(phase2_title, phase2_summary, phase2_bullets)
        if phase3_title:
            cf.phase(phase3_title, phase3_summary, phase3_bullets)
        cf.result(verdict)
        cf.footer(model)
        return cf.output()


# ── Timezone helper for import ──────────────────────────────
from datetime import timedelta


# ── Standalone usage ───────────────────────────────────────
if __name__ == "__main__":
    # Example usage
    print(CronFormat.simple(
        "system-alert-watchdog",
        "System health", "All checks passed",
        ["Disk: 45% used", "Memory: 62% used", "Load: 0.8"],
        verdict="System nominal.",
        model="system-alert-watchdog.py"
    ))
