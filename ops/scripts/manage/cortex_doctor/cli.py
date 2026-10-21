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
    check_deployed_gate_smoke,
    check_adversarial_review,
    check_dev_repo_agents,
    check_dev_repo_claude,
    check_soul_sync,
    check_skills,
    check_crons,
    check_scripts,
    check_services,
    check_metrics_arrival,
    check_system,
    check_config,
    check_nginx,
    check_nginx_dir_purity,
    check_governance,
    check_hook_drift,
    check_local_hooksPath_overrides,
    check_pinned_hooks_fresh,
    check_install,
    check_install_sh_refs,
    check_stale_deploys,
    check_repo_local_cortex_dir,
    check_stale_skills,
    check_deploy_checksums,
    check_script_naming,
    check_skills_version,
    check_skill_fences,
    check_skill_stubs,
    check_task_db,
    check_task_lifecycle_v2,
    check_skill_drift,
    check_mycortex_parity,
    check_mem_plugins,
    check_cron_runtime_scripts,
    check_langfuse_observability,
    check_restraint_registry,
    check_bus_grant_expiry,
    check_cortex_gateway,
    check_cortex_env,
    check_cron_bridge_migration,
    check_orphan_cycle_resolution,
    check_paused_cron_reasons,
    check_review_provenance,
    check_stale_loop_gov_daemon,
    check_task_id_hygiene,
    check_harness_registry,
)
from .fix import apply_fixes
from .bus_alert import dispatch_bus_alerts
from .task_integrity import check_task_model_integrity
from . import dispositions


def _flag_value(flag: str) -> str:
    """Value of ``--flag <value>`` (or ``--flag=<value>``) from argv, else "".

    The CLI parses its flags as a set, which cannot carry values; this reads the value forms
    without disturbing that.
    """
    argv = sys.argv[1:]
    for i, tok in enumerate(argv):
        if tok == flag and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith(flag + "="):
            return tok.split("=", 1)[1]
    return ""


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
    list_dispositions = "--dispositions" in args
    want_disposition = _flag_value("--disposition")
    # FAIL-SOFT read (see cortex_doctor.dispositions): an unreadable store reports everything as
    # undisposed, which is the visible direction, and must never stop a doctor run.
    res.dispositions = dispositions.load()

    all_checks = [
        check_repo,
        check_deployed_gate_smoke,
        check_adversarial_review,
        check_dev_repo_agents,
        check_dev_repo_claude,
        check_soul_sync,
        check_skills,
        check_crons,
        check_scripts,
        check_services,
        check_metrics_arrival,
        check_system,
        check_config,
        check_nginx,
        check_nginx_dir_purity,
        check_governance,
        check_harness_registry,
        check_local_hooksPath_overrides,
        check_install,
        check_install_sh_refs,
        check_stale_deploys,
        check_repo_local_cortex_dir,
        check_stale_skills,
        check_deploy_checksums,
        check_script_naming,
        check_skills_version,
        check_skill_fences,
        check_skill_stubs,
        check_task_db,
        check_task_lifecycle_v2,
        check_skill_drift,
        check_mycortex_parity,
        check_mem_plugins,
        check_hook_drift,
        check_cron_runtime_scripts,
        check_langfuse_observability,
        check_restraint_registry,
        check_bus_grant_expiry,
        check_cortex_gateway,
        check_cortex_env,
        check_cron_bridge_migration,
        check_orphan_cycle_resolution,
        check_paused_cron_reasons,
        check_review_provenance,
        check_task_model_integrity,
        check_stale_loop_gov_daemon,
        check_task_id_hygiene,
        ]

    if do_quick:
        all_checks = [
            check_repo,
            check_dev_repo_agents,
            check_dev_repo_claude,
            check_soul_sync,
            check_crons,
            check_scripts,
            check_services,
            check_system,
            check_config,
            check_governance,
            check_harness_registry,
            check_hook_drift,
            check_local_hooksPath_overrides,
            check_pinned_hooks_fresh,
            check_install,
            check_skill_stubs,
        ]
        if not res.json_mode:
            print("Hermes Cortex Doctor — Quick Check")

    if list_dispositions:
        store = dispositions.load()
        if not store:
            print("No doctor dispositions recorded — every warning/info check is UNDISPOSED.")
            sys.exit(0)
        for name in sorted(store):
            entry = store[name]
            print(f"  {name}: {dispositions.describe(name, store)}"
                  f"  reason: {entry.get('reason', '')}")
        sys.exit(0)

    if want_disposition:
        # Run the checks FIRST, so the record is validated against the CURRENT state: a name that
        # does not exist must not create a phantom disposition, and 'fixed' must not be claimed
        # while the check still warns (review findings ADV-0-1/ADV-0-3).
        for fn in all_checks:
            fn(res)
        try:
            rec = dispositions.record(want_disposition, _flag_value("--as"),
                                      _flag_value("--owner"), _flag_value("--reason"),
                                      checks=res.checks)
        except dispositions.DispositionError as e:
            # NOT soft, deliberately (review finding ADV-0-2): an explicit record that failed must
            # be visible and non-zero, or the caller believes a decision was recorded that was not.
            print(f"  ❌ disposition NOT recorded: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"  ✅ recorded: {want_disposition} → {rec['disposition']} (owner {rec['owner']})")
        res.dispositions = dispositions.load()
        print(f"     {len(res.undisposed())} warning/info check(s) still undisposed")
        sys.exit(0)

    if do_watch:
        while True:
            res = Results()
            res.json_mode = False
            res.show_fixes = not compact
            res.dispositions = dispositions.load()
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
