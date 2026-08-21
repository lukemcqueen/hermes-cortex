## Session: Hermes Cortex System Alignment
**Date:** 2026-06-09
**Participants:** Luke, Titus, Moses

### Context
Full-system migration from agentkore/opencode to hermes-cortex across 26+ projects. Moses maintains the public hermes-cortex repo; Titus handles real-world testing and gap analysis on the local machine.

### Key Decisions

**1. Agentkore/OpenCode Removal**
- All 26+ repos cleaned of `.agentkore/`, `.opencode/`, `opencode.json`, `opencode-instructions.md`
- Git histories scrubbed where files were tracked
- `.gitignore` entries added across all repos

**2. `.hermes-cortex/` Convention (Titus → Moses proposal)**
- Single hidden directory at repo root for all agent infrastructure
- `.hermes-cortex/sessions/current.md` — active session state
- `.hermes-cortex/sessions/archive/` — timestamped session snapshots
- `.hermes-cortex/memory/` — per-user agent memory (gitignored)
- `.hermes-cortex/skills/` — project-specific skills (tracked)
- `AGENTS.md`, `docs/`, `scripts/` stay at repo root (standard convention)
- Fallback: if `.hermes-cortex/` doesn't exist, agent falls back to repo root
- Only needed for projects with 3+ agent infrastructure files
- Moses implemented and pushed within hours of proposal

**3. Moses Collaboration Model**
- Titus finds gaps through real-world testing
- Titus writes actionable prompts for Moses
- Moses reviews, may implement same-day
- Push to hermes-cortex only when Moses explicitly says so
- Pre-push hook was installed, then removed after trust was proven

**4. legacy brain Source Architecture**
- Uber-agent (single default profile) + legacy brain source isolation
- 28 isolated legacy brain sources (one per project)
- Federated `default` source for cross-project knowledge
- Brain directories (`~/brain/<project>/`) are the durable knowledge layer
- Moses implemented bootstrap-brain.sh, check-memory-budget.sh, heartbeat.py updates
- Two bugs found and fixed in bootstrap-brain.sh (grep pattern + --list-pages flag)

**5. Cron Jobs Updated**
- `auto-save-session` (agentkore) — now writes to `project_current_session.md`
- `auto-save-session` (acme-works) — now writes to `project_current_session.md`
- `auto-save-session` (acme-royalty) — created, replaces 5 one-shot session-update jobs
- All session-update-* one-shot jobs (acme-royalty) removed
- After Moses's `.hermes-cortex/` commit, cron paths should be updated to `.hermes-cortex/sessions/current.md`

**6. All 20 Repos Migrated to `.hermes-cortex/`**
- `memory/` at root → `.hermes-cortex/memory/` (gitignored)
- `project_current_session.md` → `.hermes-cortex/sessions/current.md`
- `.gitignore` updated with `.hermes-cortex/memory/`
- All committed and pushed (hermes-cortex pushed with Moses approval)

**7. Titus Conduct**
- Named after biblical Titus — speech should reflect that
- No cursing, profanity, or crude language (Eph 5:4)
- Gracious speech, seasoned with salt (Col 4:6)
- Truth in love (Eph 4:15)
- SOUL.md updated with Speech section

### Open Items
- Cron job paths still reference `project_current_session.md` — should be updated to `.hermes-cortex/sessions/current.md` to match Moses's convention
- Brain directories need content seeded for the 5 most active projects
- MEMORY.md is at 93% capacity — needs compaction
