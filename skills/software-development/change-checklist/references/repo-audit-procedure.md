# Repo Audit Procedure — Full-System Gap Analysis

A structured cross-dimensional scan of an entire repo for gaps, stale references,
count inaccuracies, formatting issues, and structural drift. Use this when the
user asks for a "final check" or "full audit" of the repo, or before a release.

## Dimension Map

| # | Dimension | What You Survey | Key Tools |
|---|-----------|----------------|-----------|
| 1 | **Repo tree** | Directory structure, recent commits, uncommitted changes, stale legacy dirs | `find`, `git log`, `git status`, `search_files` |
| 2 | **Documentation** | DOCS-INDEX cross-references (every path against filesystem), README counts vs reality, template freshness | `read_file` + `test -f` for every DOCS-INDEX entry |
| 3 | **SOUL freshness** | Template vs deployed drift, missing sections, content that leaked between agent profiles, Final Directive gaps | `diff`, section headers check |
| 4 | **Cron health** | All active jobs, naming consistency, schedule accuracy, failure rate | `cronjob action=list`, `fleet-reference.md` cross-check |
| 5 | **Governance cycles** | Stale locks, PENDING cycles (orphaned), long-term scoring trends | `cycle_query`, `check_lock`, `cycle_stats` |
| 6 | **Service health** | System-level validation (doctor, nginx, services, ports) | `cortex-doctor.py --quiet` |
| 7 | **Symlink integrity** | Broken symlinks, PII-leaking absolute paths (e.g. `~/`), legacy path references | `symlink-audit.sh` or manual `find -L` |

## Procedure

### Phase 1: Survey the Whole Tree

```python
# Batch independent reads in one turn:
terminal("find . -maxdepth 3 -type d | grep -v ...")
terminal("git log --oneline -10")
terminal("git status --short")
search_files(pattern="**/*.md", target="files", path=".")
```

Key signals:
- **Stale `src/` directories** that should be `ops/` or `runtime/`
- **Legacy layering** — code that was restructured but has leftover references
- **Script count** — `.py` + `.sh` total to compare against README claims

### Phase 2: Cross-Reference DOCS-INDEX

Every DOCS-INDEX.md entry must point to an existing path. The technique:

```
for each line in DOCS-INDEX.md:
  extract the `` `path` `` reference
  test -f "$path" || test -d "$path" || flag MISSING
```

Also check for:
- **PII leaks** — paths containing `~/`, `~/`, or other absolute user homes in a public-facing doc
- **Formatting decay** — extra `|||` pipe prefixes that break table rendering

### Phase 3: Check README Accuracy

The README decays faster than any other doc. Verify three things:
1. **Counts** — "37 cron jobs" vs actual `cronjob action=list` count
2. **Version** — badge version matches latest git tag
3. **Install commands** — referenced script paths exist and aren't stale

### Phase 4: SOUL Freshness Check

Compare each agent's `SOUL.md` against the template:
- **Missing sections** — template has a `## Section` the agent file lacks
- **Extra sections** — agent file has content the template doesn't define (not always bad, but flag it)
- **Content leaks** — template should be generic; agent-specific content (names, orgs, machines) in the template must be stripped
- **Numbering gaps** — behavioural principles should be sequential

Fix pattern: patch the agent SOUL.md first (repo), then `cp` to `~/.hermes/SOUL.md`
(deployed runtime copy).

### Phase 5: Governance Cycle Scan

```python
cycle_stats(days=7)       # overall health
cycle_query(limit=10)     # look for PENDING / orphaned cycles
check_lock()              # stale locks
```

Three types of orphans:
1. **PENDING with non-zero outcome_note** — completed work, never scored. `feedback_accept` to close.
2. **PENDING with empty outcome_note** — maybe incomplete. Check session history.
3. **Lock file present but MCP lock absent** — dangling `.governance-generic.json` symlink. `rm -f` it.

### Phase 6: Run the Doctor

Always cap the audit with:
```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
```

Fix any warnings in priority order:
1. **Stale lock** → remove dangling `.governance-generic.json` symlink
2. **Symlinks** → run `symlink-audit.sh`, fix each broken link
3. **Repo clean** → commit outstanding changes

### Phase 7: Report

Deliver a structured summary with:
- **✅ HEALTHY / ⚠️ WARNING / ❌ FAIL** — single-line verdict
- **Count table** — items checked, each with green/yellow/red
- **Action items** — numbered, sorted by priority (HIGH/MEDIUM/LOW)
- **Effort estimate** — per-action "~5 min" / "~30 min" so user can triage
