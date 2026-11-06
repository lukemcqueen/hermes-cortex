# Repo Consolidation — Evidence (2026-11-06)

Recorded command output backing the consolidation proposal
(`docs/design/repo-consolidation-proposal.md`).

## 1. Live `src/` refs in `core/` (slice-4 purge scope)

Command: `git grep -n 'src/' -- core/`

```
core/governance/__init__.py:5:The legacy location at src/loop-governance/ is a backward-compat shim.
core/governance/score_cycle.py:26:      --code-file src/impl.py \
core/governance/score_cycle.py:40:      --code-file src/impl.py \
core/governance/score_cycle.py:41:      --prev-code-file src/impl.prev.py \
core/governance/score_cycle.py:51:      --code-file src/impl.py --json
core/governance/score_cycle.py:88:  cycle-logger --task feature-x --cycle 1 --code-file src/main.py --json
```

Classification: `__init__.py:5` = stale backward-compat shim note (shim retired
with `src/`) — DELETE the note. `score_cycle.py:26,40,41,51,88` = GENERIC
`--code-file` example args in docstrings (not a path to this repo's tree) —
re-exemplify to a neutral path.

## 2. `src/` in `skills/` (exemption classification)

Command: `git grep -ln 'src/' -- skills/`

```
skills/autonomous-ai-agents/grok/SKILL.md
skills/autonomous-ai-agents/hermes-cortex-setup/SKILL.md
skills/autonomous-ai-agents/openhands/SKILL.md
skills/devops/agent-harness-design/SKILL.md
skills/devops/agent-harness-design/references/reference-implementations.md
skills/devops/agent-health-monitoring/references/agent-registry-structure.md
skills/devops/auto-remediation/references/stale-required-scripts.md
skills/devops/codebase-portability/SKILL.md
skills/devops/codebase-portability/references/cortex-path-migration-july2026.md
skills/devops/codebase-portability/references/hermes-cortex-path-audit.md
```

Classification: each occurrence is a generic or third-party `src/` path (another
project's tree, an example repo, or a foreign-project reference) — NONE points
at this repo's retired `src/` tree. Exempt from the purge; re-checked per file
during slice 4.

## 3. `poll-bus-inbox_titus.sh` — live-tool verification (source)

Command: `head -30 poll-bus-inbox_titus.sh`

```
#!/usr/bin/env bash
# Agent Bus poll — inbox_titus
# Reads credentials from hermes-inbox.conf; never embeds secrets.
# Usage: ./poll-bus-inbox_titus.sh
# Correct behavior: exits 0 on ANY successful authenticated queue read (2xx) ...
CONF="${HC_INBOX_CONF:-$HOME/.steadfaste-fleet/hermes-inbox.conf}"
[ -r "$CONF" ] || { echo "ERROR: cannot read $CONF" >&2; exit 1; }
URL="$(awk -F= '/^CORTEX_BUS_URL=/{sub(/^[^=]*=/,""); print}' "$CONF")"
AUTH="$(awk -F= '/^CORTEX_BASIC_AUTH=/{sub(/^[^=]*=/,""); print}' "$CONF")"
...
BODY="$(curl -sS --fail-with-body -m 25 -u "$AUTH" "$URL/api/pgmq/peek/inbox_titus")"
```

Classification: a LIVE agent-bus poll tool (reads
`$HOME/.steadfaste-fleet/hermes-inbox.conf`, curls the `inbox_titus` queue) —
relocate to `ops/scripts/poll-bus-inbox_titus.sh`, do NOT delete.