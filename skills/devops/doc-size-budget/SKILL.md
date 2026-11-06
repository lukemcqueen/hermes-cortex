---
name: doc-size-budget
description: "Slim docs and always-loaded skills to byte targets."
version: 1.0.0
author: Steadfaste Fleet
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [docs, compression, size-budget, soul, agents, governance]
    related_skills: [doc-freshness, soul-refinement, documentation-auditing]
---

# Doc Size Budget — Compress Without Breaking Consumers

## What This Is

Instruction docs (SOUL.md, AGENTS.md) carry byte budgets — for SOUL.md enforced
through 2026-11-04 by the doctor (WARN >15K, FAIL >20K), and since then only by
explicit user targets ("keep SOUL for loading", "get AGENTS to 10k"). The
fleet-side SOUL enforcers (`_extract_soul_markers`, `check_soul_sync`,
`soul-merge.py`) were **removed 2026-11-04** with the SOUL-decoupling —
`~/.hermes/SOUL.md` is Hermes-owned and nothing fleet-side auto-syncs or
size-gates it. Shrinking AGENTS.md (per-repo) and SOUL.md is therefore now
free-form editing constrained mainly by the `agents-doc-audit` heading gate and
by not changing behaviour.

## When to Use

- User asks to slim SOUL.md / AGENTS.md / a template to a byte target
- Consolidating or merging template principles/sub-points
- Any doc whose propagation is governed by an audit regex gate

## Know What Each Enforcement Layer Counts — BEFORE Cutting

| Layer | What it counts | Wrong trim's consequence |
|-------|---------------|--------------------------|
| agents-doc-audit | heading regexes (`^## Identity`, `^## Core Mission`, …) | Removing a heading = commit-gate FAIL |
| (removed 2026-11-04) | `_extract_soul_markers` / `check_soul_sync` / `soul-merge.py` — the doctor no longer checks SOUL markers, principle titles, or size | none — SOUL is Hermes-owned, free-form |

**Safe to compress freely (proven 2026-08-19: SOUL template 14,737 → 10,032 B):**
- Preambles and continuation prose after bold markers.
- Merge a redundant sub-point INTO an existing one under the EXISTING marker
  name — never introduce a new marker name.
- Scripture entries: keep ONE anchor (the LAST `### Book —` is the daily-bible
  cron's next-book anchor); archive the rest to `~/brain/<agent>/bible/`.

## Process Discipline (Hard Lesson)

Luke 2026-08-19: "You are literally WASTING MONEY!" — an agent looped rewriting
the same file from memory while claiming to compress; byte count never changed.

- Apply compressions as **programmatic replacements against the on-disk file**
  (Python `str.replace`), then `wc -c`. Never rewrite the whole file from memory
  each iteration — the model silently re-pastes identical bytes.
- Verify the byte count actually CHANGED and count applied replacements
  (`applied: n / total`) before declaring progress. Print a per-section size
  breakdown to find the real fat instead of guessing.
- Stop when the user says "enough" — don't chase the last 100 bytes.

## Procedure

1. **Survey** — `read_file` the original; measure `wc -c`; enumerate the
   mandatory anchors (headings) and marker lines that must survive.
2. **Verify invariants programmatically** — count principle titles
   (`re.findall(r'^### \d+\.', text, re.M)`), trait bullets
   (`r'^- \*\*([^*]+)\*\*'`), sub-point markers (`r'^\*\*([^*]+)\*\*'`), and
   every mandatory section heading. Save the counts.
3. **Compress by replacement** — Python script with a list of (old, new) pairs
   applied via `str.replace`, counting hits and misses. Re-measure.
4. **Re-verify invariants** — same counts as step 2 (or deliberate, documented
   deltas).
5. **Verify** — run `agents-doc-audit.py --repo . --json` (missing sections ==
   []). SOUL is Hermes-owned — trim the deployed `~/.hermes/SOUL.md` itself if
   it must shrink; there is no fleet-side sync to refresh it (soul-merge
   removed 2026-11-04).
6. **Commit + push** — pre-push hook requires deployed == repo checksum, so run
   `fleet-update.sh` BEFORE `git push` (doc changes: the enforcement chain is
   commit → deploy → push).

## Always-Loaded Skill Budget (the budget nothing enforces)

SOUL/AGENTS have a ceiling the doctor enforces; the `always:` list in `skills.yaml` has none,
and its bytes are paid by EVERY session of EVERY agent — so the set grows one well-justified
paragraph at a time and nothing ever fails. Measure the set before touching it:

```bash
python3 - <<'EOF'
import yaml
from pathlib import Path
repo = Path("<repo>")
total = 0
for name in yaml.safe_load(open(repo / "skills.yaml"))["always"]:
    p = next((repo / "skills").rglob(f"{name}/SKILL.md"))
    total += p.stat().st_size
    print(f"{p.stat().st_size:7d}  {name}")
print(f"{total:7d}  TOTAL  (~{total // 4} tokens per session)")
EOF
```

- **Set a per-skill byte target explicitly, because nothing enforces one.** The outlier is the
  budget problem, not a uniform trim: when one always-loaded skill holds more than half the
  set's bytes, that skill is the fix. An always-loaded body carries the RULES; depth a session
  needs only sometimes belongs in `references/`, which the loader does not read until asked.
- **Land a reduction as MOVE-ONLY edits first, then reword in a separate pass.** A reviewer can
  verify "the body shrank and the content is byte-identical at its new path"; moving and
  rewriting in one commit makes neither checkable, which is how a trim gets deferred forever.
- **Never reach a byte target by deleting a rule that changes behaviour.** That trades a
  measurable cost for an unmeasurable one. Move it, cut redundant restatements, or cut prose.

## Pitfalls

- **Rewriting from memory** re-pastes identical bytes — always edit on-disk via
  programmatic replace and verify the byte delta.
- **Pushing before cortex-update** — pre-push hook fails "Checksum: AGENTS.md"
  when deployed != repo. Deploy first.
- **AGENTS.md / SOUL.md are no longer auto-synced** (soul-merge / soul-sync
  removed 2026-11-04) — there is no fleet-side copy to diverge from; edit each
  file where it lives.

## Verification

- `wc -c docs/templates/SOUL.md` ≤ target (a user target; no doctor FAIL since 2026-11-04)
- `agents-doc-audit.py --repo . --json` → `missing_sections: []`
- Always-set measured per skill AND in total, with no single skill dominating the total
- `git log --oneline -1 origin/main` shows the pushed commit
