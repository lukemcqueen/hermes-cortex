"""
CLI entry point for cortex-doctor.

Parses arguments, runs checks, optionally fixes issues,
sends bus alerts, and prints summaries.
"""

import sys
import time

from .results import Results
from .checks import (
    check_repo,
    check_dev_repo_agents,
    check_soul_sync,
    check_skills,
    check_crons,
    check_scripts,
    check_services,
    check_system,
    check_config,
    check_nginx,
    check_nginx_dir_purity,
    check_governance,
    check_hook_drift,
    check_local_hooksPath_overrides,
    check_pinned_hooks_fresh,
    check_install,
    check_stale_deploys,
    check_stale_skills,
    check_deploy_checksums,
    check_script_naming,
    check_skills_version,
    check_skill_fences,
    check_skill_stubs,
    check_task_db,
    check_skill_drift,
    check_mycortex_parity,
    check_cron_runtime_scripts,
)
from .fix import apply_fixes
from .bus_alert import dispatch_bus_alerts


def main():
    args = set(sys.argv[1:])
    res = Results()
    res.json_mode = "--json" in args
    res.show_fixes = "--quiet" not in args
    do_fix = "--fix" in args
    do_watch = "--watch" in args
    do_bus_alert = "--bus-alert" in args
    do_quick = "--quick" in args
    compact = "--quiet" in args

    all_checks = [
        check_repo,
        check_dev_repo_agents,
        check_soul_sync,
        check_skills,
        check_crons,
        check_scripts,
        check_services,
        check_system,
        check_config,
        check_nginx,
        check_nginx_dir_purity,
        check_governance,
        check_local_hooksPath_overrides,
        check_install,
        check_stale_deploys,
        check_stale_skills,
        check_deploy_checksums,
        check_script_naming,
        check_skills_version,
        check_skill_fences,
        check_skill_stubs,
        check_task_db,
        check_skill_drift,
        check_mycortex_parity,
        check_hook_drift,
        check_cron_runtime_scripts,
    ]

    if do_quick:
        all_checks = [
            check_repo,
            check_dev_repo_agents,
            check_soul_sync,
            check_crons,
            check_scripts,
            check_services,
            check_system,
            check_config,
            check_governance,
            check_hook_drift,
            check_local_hooksPath_overrides,
            check_pinned_hooks_fresh,
            check_install,
            check_skill_stubs,
        ]
        if not res.json_mode:
            print("Hermes Cortex Doctor — Quick Check")

    if do_watch:
        while True:
            res = Results()
            res.json_mode = False
            res.show_fixes = not compact
            for fn in all_checks:
                fn(res)
            res.print_summary(compact=compact)

            if not res.json_mode and (res.warn_count > 0 or res.fail_count > 0):
                print("  ═══════════════════════════════════════════════════")
                print("  🔧 REQUIRED ACTIONS — resolve each ⚠️  or ❌ above")
                print()
                needs_fix = [c for c in res.checks if c["status"] != "PASS" and c["fix"]]
                if needs_fix:
                    for c in needs_fix:
                        print(f"    {c['fix']}")
                print()
                print("  After resolving, run doctor again to confirm.")
                print("  ═══════════════════════════════════════════════════\n")
                time.sleep(30)
    else:
        for fn in all_checks:
            fn(res)
        if do_bus_alert:
            dispatch_bus_alerts(res)
        res.print_summary(compact=compact)

        if not res.json_mode and (res.warn_count > 0 or res.fail_count > 0):
            print("  ═══════════════════════════════════════════════════")
            print("  🔧 REQUIRED ACTIONS — resolve each ⚠️  or ❌ above")
            print()
            needs_fix = [c for c in res.checks if c["status"] != "PASS" and c["fix"]]
            if needs_fix:
                for c in needs_fix:
                    print(f"    {c['fix']}")
            print()
            print("  After resolving, run doctor again to confirm.")
            print("  ═══════════════════════════════════════════════════\n")

        if do_fix:
            apply_fixes(res)
            res2 = Results()
            res2.json_mode = res.json_mode
            res2.show_fixes = res.show_fixes
            for fn in all_checks:
                fn(res2)
            if not res2.json_mode:
                print("\n  ── Post-fix recheck ──")
            res2.print_summary(compact=compact)

    if res.fail_count > 0:
        sys.exit(2)
    elif res.warn_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)
