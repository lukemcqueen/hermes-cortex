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
        # name -> disposition record. Set by the CLI from the store; empty means "nothing is
        # disposed", which is the visible direction (see cortex_doctor.dispositions).
        self.dispositions = {}

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

    def undisposed(self):
        """WARN/INFO checks with no live disposition — what still needs a decision.

        Imported lazily so a broken dispositions module can never stop the doctor: a run that
        cannot work out what is disposed reports everything as undisposed, which is the visible
        direction, and never a silent pass.
        """
        try:
            from .dispositions import undisposed as _undisposed
        except Exception:  # noqa: BLE001 — the doctor must run whatever the state of this module
            return [c for c in self.checks if c["status"] in ("WARN", "INFO")]
        return _undisposed(self.checks, self.dispositions)

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
            # A warning somebody has DECIDED about says so, printed by the tool rather than
            # asserted by the agent: that is the difference this mechanism exists to make.
            if c["status"] in ("WARN", "INFO") and c["name"] in self.dispositions:
                try:
                    from .dispositions import describe
                    label += f"  [{describe(c['name'], self.dispositions)}]"
                except Exception:  # noqa: BLE001
                    pass
            if compact:
                print(f"  {label}")
            else:
                detail = f" — {c['detail']}" if c["detail"] else ""
                print(f"  {label}{detail}")
                if self.show_fixes and c["fix"] and c["status"] != "PASS":
                    print(f"         🔶 Suggestion: {c['fix']}")

        total = self.pass_count + self.warn_count + self.fail_count + self.info_count
        overall = "HEALTHY"
        if self.fail_count > 0:
            overall = "FAILING"
        elif self.warn_count > 0:
            overall = "WARNING"
        icon_map = {"HEALTHY": "✅", "WARNING": "⚠️ ", "FAILING": "❌"}
        und = self.undisposed()
        # The undisposed count goes OUTSIDE the parenthetical on purpose: the four counts inside it
        # are parsed by a consumer regex (tests/test_dogfood_pipeline.py), and a fifth entry inside
        # the parens silently stops that match. Additions go beside, never inside.
        und_note = f"  · {len(und)} undisposed" if und else ""
        print(
            f"\n  {icon_map[overall]} Overall: {overall}  "
            f"({self.pass_count} pass · {self.warn_count} warn · "
            f"{self.fail_count} fail · {self.info_count} info){und_note}\n"
        )

        # UNDISPOSED (2026-10-20). Deferring a warning stays legitimate — it is not a FAIL and no
        # gate reads it — but it has to be a decision with a name on it. Printed in COMPACT mode
        # too: --quiet is what the update path runs, and that is exactly where the gloss-over
        # happened.
        if und:
            print(f"  🧹 UNDISPOSED — {len(und)} warning/info check(s) nobody has decided about")
            print("     Fix it, or record the decision (one command each):")
            for c in und[:12]:
                print(f"       · {c['name']}")
                if c.get("fix"):
                    print(f"         fix: {c['fix']}")
                print(f"         or:  cortex-doctor.py --disposition \"{c['name']}\" --as deferred "
                      f"--owner <you> --reason \"<why>\"")
            if len(und) > 12:
                print(f"       … and {len(und) - 12} more")
            print("     A disposition EXPIRES and is reported as STALE until it is renewed — "
                  "deferring is fine, forgetting is not.")
            print()
