---
name: cron-script-naming-reconciliation
version: 1.1.0
category: devops
description: Reconcile cron/script names, prefixes, skill versions.
platforms: [linux]
---

# Cron-Script Naming Reconciliation

## When to Use

- User asks to match cron name and script name
- User asks to enforce agent-/orch-/local- prefix rules on scripts
- User asks to check all repo skills have a version field
- Periodic naming audit
- Before major refactors

## Audit Phase

1. List all crons and their scripts via cronjob action=list
2. For each cron, check if the script basename matches the cron name
3. Flag scripts lacking prefix convention
4. Check all repo skills for version field in frontmatter

## Fix: Script Rename

1. Grep all refs across repo
2. Git mv the file
3. Patch install scripts script ref in create_cron
4. Patch cortex-update.sh register src AND dest paths
5. Patch docs references
6. cronjob action=update job_id script=new-name
7. bash ops/scripts/cortex-update.sh
8. python3 ops/scripts/manage/cortex-doctor.py --quiet

## Fix: Cron Rename

1. cronjob action=remove
2. Update create_cron block cron name
3. Update uninstall array cron name
4. cronjob action=create with same settings
5. Fix-cron-duplicates.py for array sync
6. Check docs refs
7. Run doctor to verify

## Doctor Checks Added

- Script naming: cron name matches script name
- Script prefix: script has matching prefix
- Skill version: all skills have version field

## Additional

- Stale deploy cleanup: cortex-update.sh --clean-stale
- Doctor parse_expected_crons reads uninstall arrays
- Update both arrays on rename