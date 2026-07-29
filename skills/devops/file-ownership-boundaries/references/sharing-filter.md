# Sharing Filter — Reference

## Decision Flow

```
Item being evaluated for upstreaming/sharing
│
├── Is it a Hermes default skill? (no source in our repo)
│   ├── YES → ❌ STOP. Not ours to share.
│   └── NO  →
│
├── Is it already in hermes-cortex repo?
│   ├── YES → Is there a SUBSTANTIVE change since last sync?
│   │   ├── YES → ✅ Share the delta (new step, pitfall, section)
│   │   └── NO  → ❌ Skip. Already shared with fleet.
│   └── NO  →
│
└── Is it a new hermes-cortex skill or support file?
    ├── YES → ✅ Share
    └── NO  → ❌ Skip (ephemeral, PII, one-off)
```

## Examples from Practice

| Scenario | Verdict | Why |
|----------|---------|-----|
| Patch to `task-start` (framework-owned) | ❌ Skip | Framework-owned, gets overwritten |
| New `todo-persistence` skill in repo | ✅ Share | New reusable capability |
| Added todo step to `agent-fundamentals` (our skill) | ✅ Share delta | Substantive improvement |
| One-line doc fix to existing repo skill | ❌ Skip | Already shared, no new value |
| Session-specific workaround for missing package | ❌ Skip | Ephemeral, not reusable |
| New reference doc under `change-checklist` | ✅ Share | Extends umbrella skill |

## The "Would Someone Benefit?" Test

Ask: *"Would someone running Hermes Cortex benefit from this? Or is it already available to them through either the Hermes or hermes-cortex repos?"*

If it's already available in either repo, don't share it. Sharing something that's already accessible wastes the fleet's attention and creates noise.
