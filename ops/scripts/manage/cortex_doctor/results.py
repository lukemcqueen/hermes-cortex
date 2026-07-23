"""
Result tracking for cortex-doctor.

Collects check results, computes pass/warn/fail/info counts,
and prints formatted output (human-readable or JSON).
"""

import json
import os
import subprocess
from datetime import datetime, timezone

from .config import CORTEX_REPO


class Results:
    def __init__(self):
        self.checks = []
        self.pass_count = 0
        self.warn_count = 0
        self.fail_count = 0
        self.info_count = 0
        self.json_mode = False
        self.show_fixes = True

    def add(self, name, status, detail="", fix=""):
        self.checks.append({"name": name, "status": status, "detail": detail, "fix": fix})
        if status == "PASS":
            self.pass_count += 1
        elif status == "WARN":
            self.warn_count += 1
        elif status == "FAIL":
            self.fail_count += 1
        elif status == "INFO":
            self.info_count += 1

    def status_icon(self, s):
        if self.json_mode:
            return s
        return {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "SKIP": "➖", "INFO": "ℹ️ "}.get(s, "❓")

    def print_summary(self, compact=False):
        if self.json_mode:
            agent = os.environ.get("AGENT_NAME", "")
            if not agent:
                try:
                    agent = subprocess.run(
                        ["hostname"], capture_output=True, text=True
                    ).stdout.strip()
                except Exception:
                    agent = "unknown"
            try:
                git_sha = subprocess.run(
                    ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            except Exception:
                git_sha = ""
            version_file = CORTEX_REPO / "VERSION"
            version = version_file.read_text().strip() if version_file.exists() else ""
            healthy = self.fail_count == 0 and self.warn_count == 0
            print(
                json.dumps(
                    {
                        "summary": {
                            "pass": self.pass_count,
                            "warn": self.warn_count,
                            "fail": self.fail_count,
                            "info": self.info_count,
                        },
                        "checks": self.checks,
                        "agent": agent,
                        "git_sha": git_sha,
                        "version": version,
                        "healthy": healthy,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    indent=2,
                )
            )
            return

        print(
            f"\n━━━ Hermes Cortex Doctor ━━━  ({datetime.now().strftime('%H:%M:%S')})\n"
        )

        for c in self.checks:
            icon = self.status_icon(c["status"])
            label = f"{icon} {c['name']}"
            if compact:
                print(f"  {label}")
            else:
                detail = f" — {c['detail']}" if c["detail"] else ""
                print(f"  {label}{detail}")
                if self.show_fixes and c["fix"] and c["status"] != "PASS":
                    print(f"         → {c['fix']}")

        total = self.pass_count + self.warn_count + self.fail_count + self.info_count
        overall = "HEALTHY"
        if self.fail_count > 0:
            overall = "FAILING"
        elif self.warn_count > 0:
            overall = "WARNING"
        icon_map = {"HEALTHY": "✅", "WARNING": "⚠️ ", "FAILING": "❌"}
        print(
            f"\n  {icon_map[overall]} Overall: {overall}  "
            f"({self.pass_count} pass · {self.warn_count} warn · "
            f"{self.fail_count} fail · {self.info_count} info)\n"
        )
