# Repo Consolidation — Target Structure (PROPOSAL, 2026-11-06)

> Operator decision (2026-11-06): keep the `ops/` layer model (NOT a `src/`
> revival — src/ was deliberately retired in P0a/P0d: `b416ed5c`, `0e5be574`,
> `f51df21a`, `7e8a8eac`, `05f6ff68`), REMOVE the stale reference once and for
> all, and CONSOLIDATE ("less ways to get confused"). This is the concrete
> target; pro-reviewed before any move.

## Target top-level (5 directories + files)

```
steadfaste-fleet/
├── AGENTS.md            # agent entry point (nav section rewritten)
├── CLAUDE.md            # thin pointer → AGENTS.md (Claude Code auto-loads it)
├── README.md / CONTRIBUTING.md / LICENSE / VERSION / skills.yaml / pytest.ini
├── REPO-MAP.md          # NEW — the single 30-second map of where things are
├── ops/                 # ALL operational source (12 subtrees, see map)
│   ├── core/            # ← from top-level core/ (fleet_bus, governance)
│   ├── tools/           # ← from top-level tools/ (fleet-search, auto-remediation-scan)
│   ├── evals/           # ← from top-level evals/
│   ├── mcp-servers/     # ← from top-level mcp-servers/ (6 servers)
│   ├── scripts/         # + poll-bus-inbox_titus.sh moves here (live bus-poll tool)
│   ├── install/  offline/  services/  evidence/  web-cache/  deploy/   # unchanged
│   └── config/          # ← from top-level config/ (jev-router-models.json)
├── plugins/             # Hermes plugins (distinct deployable artifacts; stays top-level)
├── skills/               # canonical skill library (unchanged)
├── docs/                 # docs (incl. evidence/ — NEVER pruned, per keep-logs rule)
└── tests/                # test suite (unchanged)
```

Consolidation removes four top-level directories (`core/`, `tools/`, `evals/`,
`mcp-servers/`) and three stray top-level dirs (`config/`, `laptop/`,
`profiles/`) — a fresh agent sees exactly five trees, each with one obvious
meaning.

## Stray-file relocations

| File | From | To |
|---|---|---|
| `poll-bus-inbox_titus.sh` | root | `ops/scripts/poll-bus-inbox_titus.sh` (live tool — verified: reads `~/.steadfaste-fleet/hermes-inbox.conf`, polls `inbox_titus`) |
| `evidence-bus-poll-titus-20261009.md`, `evidence-agent-fixer-evening-repetition-loop-20261009.md` | root | `docs/evidence/` |
| `jev-router-models.json` | `config/` | `ops/config/jev-router-models.json` |
| `lightdm-screen-blank` | `laptop/usr-local-bin/` | `ops/install/laptop/lightdm-screen-blank` (host-file artifact kept in repo) |
| `profiles/README.md` | `profiles/` | `docs/reference/profiles.md` (content merged into the repo map if it duplicates) |

## The stale `src/` purge — what "once and for all" means

- **THE stale reference** is the `repo-organization` skill's §2 tree (still
  prescribing `src/scripts`, `src/agent-inbox`, `src/dashboard`,
  `src/loop-governance`, `deploy/nginx`). REWRITE the skill to codify the
  actual layer model above; retire the src/ tree from it. Its naming/cron/audit
  sections stay.
- **Live code — 6 hits in 2 files** (`git grep -n 'src/' -- core/`):
  `core/governance/__init__.py:5` (backward-compat shim note for the retired
  `src/loop-governance/` — shim is gone with `src/`; delete the note) and
  `core/governance/score_cycle.py:26,40,41,51,88` (all `--code-file
  src/impl.py`-style GENERIC example args in docstrings — re-exemplify to a
  neutral path). The purge slice fixes all six.
- **Dated RECORDS stay byte-identical:** `docs/older/` (archived external
  codeharness design docs), `docs/prd/PRD-003..006` (dated PRDs),
  `docs/evidence/*` (committed evidence captures with checksums). Rewriting a
  record falsifies what was true at that revision (rename-sweep discipline);
  these are NOT live references to our retired tree. The repo map marks them
  as historical.
- **Generic/third-party `src/` usage in skills** (e.g. other projects' `src/`
  paths in skill examples) is NOT a stale reference — verified case by case
  with `git grep -ln 'src/' -- skills/` (2026-11-06: 10 files — grok,
  hermes-cortex-setup, openhands, agent-harness-design ×2, agent-health-
  monitoring, auto-remediation, codebase-portability ×3; each is a generic or
  third-party path, none points at this repo's retired tree). The purge slice
  re-runs that grep and re-checks each file before exempting it.

## Reference sweeps required by the moves (the real work)

Every move rewrites references in: `ops/scripts/cortex-update.sh` register
lines, `deploy-manifest.tsv` + `cortex_lib.paths.resolve_repo_resource`,
Hermes MCP registrations (`hermes mcp add <repo>/mcp-servers/…` — moving
`mcp-servers/` requires re-registering the live MCP servers per the
rename-sweep MCP recipe), cron jobs, tests (incl. golden-path fixtures),
DOCS-INDEX, skills that hardcode `core/`/`tools/`/`mcp-servers/` paths.

## Implementation slices (each its own governed cycle)

1. **Docs/skill**: rewrite `repo-organization` skill + write `REPO-MAP.md` +
   its generator + rewrite AGENTS.md nav + DOCS-INDEX. (No file moves — kills
   the #1 stale reference immediately.)
2. **Consolidation moves**: `core/`,`tools/`,`evals/`,`mcp-servers/` → `ops/`;
   full reference sweep; deploy-manifest + MCP re-registration; tests green;
   dogfood + doctor.
3. **Root strays**: relocations above + `CLAUDE.md` → pointer.
4. **Live src/ purge**: shim note, score_cycle examples, any live doc refs.
5. **Enforcement**: doctor check asserting the new invariant (no top-level
   `core/`/`tools/`/`evals/`/`mcp-servers/`/`config/`/`laptop/`/`profiles/`
   dirs, REPO-MAP.md present) + a `check_repo_map` freshness check (below) +
   migration runbook + fleet convergence note.

## REPO-MAP freshness (must never go stale)

The reason `repo-organization` drifted stale is that nobody enforced it after
the `src/`→`ops/` move. REPO-MAP must not repeat that:

- **Generated, not hand-maintained.** `ops/scripts/manage/regenerate-repo-map.sh`
  deterministically derives the STRUCTURAL skeleton from the tree
  (`git ls-files` top-level trees + each tree's first segment list + counts),
  and appends a human-authored purpose fragment (`REPO-MAP.purpose.md`) so the
  per-tree "what this is/for" prose is written once, not re-derived by hand.
- **Enforced, not trusted.** A doctor check `check_repo_map` FAILs when the
  committed REPO-MAP's structural skeleton diverges from `git ls-files` (a
  moved/renamed tree, a new or removed top-level, a relocation the map doesn't
  show), with a `fix:` line naming the regenerator. The map cannot silently
  drift — same enforcement pattern as the existing `skill-drift-parity` check.
- **The move sweep feeds the regenerator.** Every slice-② move and slice-③
  relocation ends by running the regenerator, so the committed map tracks the
  sweep in the same change (rename-sweep §6 spirit: ship the map update with
  the move, never as a follow-up).

## Evidence pointers

- Operator directive: Telegram DM 2026-11-06 — *"once and for all REMOVE the
  stale reference from all docs. consolidating is better (less ways to get
  confused) if you can."*
- Current layout + counts: `docs/design/repo-reorganization-survey.md`
  (`git ls-files | cut -d/ -f1 | sort | uniq -c`, commit `9cb85f27`).
- src/ retirement commits: `b416ed5c`, `0e5be574`, `f51df21a`, `7e8a8eac`,
  `05f6ff68` (`git log --oneline --diff-filter=D -- 'src/*'`).
- Live src/ refs + skill exemption + poll-script source: RECORDED in
  `docs/evidence/repo-consolidation-evidence-20261106.md` (verbatim grep output
  of `git grep -n 'src/' -- core/` and `git grep -ln 'src/' -- skills/`, with
  per-file classification, plus the poll-script source head);
- poll-bus-inbox_titus.sh verified live by reading its source (reads
  hermes-inbox.conf, curls `$URL/api/pgmq/peek/inbox_titus`).
