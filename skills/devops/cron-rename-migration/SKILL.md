---
name: cron-rename-migration
description: "Migrate bare-name crons to agent-* prefix on any agent after repo update"
trigger: "After `git pull` discovers cron naming changes in the repo"
---

# Cron Rename Migration

Use this skill on ANY agent after pulling the hermes-cortex repo that
renamed all bare-name crons to `agent-*` prefix (July 2026).

## Steps

1. **Pull and deploy full sync:**
   ```bash
   cd ~/hermes-cortex
   git pull origin main
   cortex-update.sh
   ```

2. **Sync install arrays — aligns uninstall arrays with create names:**
   ```bash
   python3 ~/.hermes-cortex/scripts/manage/fix-cron-duplicates.py --fix
   ```

3. **Install new agent-* crons (skips existing ones):**
   ```bash
   bash ~/.hermes-cortex/scripts/install-crons.sh
   ```

4. **Clean up old bare-name crons (safe — only removes no_agent crons with gone scripts):**
   ```bash
   python3 ~/.hermes-cortex/scripts/manage/fix-cron-duplicates.py --gc
   python3 ~/.hermes-cortex/scripts/manage/fix-cron-duplicates.py --gc --prune
   ```

5. **Verify:**
   ```bash
   python3 ~/.hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
   ```

## Orchestrators only (Moses, Esther)

After step 5, also run:
```bash
bash ~/.hermes-cortex/scripts/install/install-orch-crons.sh --force
```

## What GC preserves

| Type | Kept? | Reason |
|------|-------|--------|
| `local-*` crons | ✅ Always | Machine-specific, intentional |
| LLM-driven crons | ✅ Always | Can't determine intentionality |
| `no_agent` crons with existing scripts | ✅ Always | Script still needed |
| `no_agent` crons with GONE scripts | ⚠️ Pruned | Truly orphaned |

## Verify

Doctor should report **0 failures**. Expected warnings: AGENTS.md deploy sync,
SOUL.md deploy sync, legacy governance locks.
