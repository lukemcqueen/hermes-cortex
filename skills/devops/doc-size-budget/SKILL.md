---
name: doc-size-budget
description: "Slim docs to byte targets (SOUL 10K, AGENTS gates) safely."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [docs, compression, size-budget, soul, agents, governance]
    related_skills: [doc-freshness, soul-refinement, documentation-auditing]
---

# Doc Size Budget — Compress Without Breaking Consumers

## What This Is

Instruction docs (SOUL.md, AGENTS.md) carry byte budgets enforced by the doctor
(SOUL: WARN >15K, FAIL >20K) or by explicit user targets ("get SOUL to 10k").
Shrinking them is not free-form editing: enforcement layers count specific
markers, titles, and headings, and the merge tool that propagates template →
deployed copies is **add-only** — a wrong trim permanently WARNs/FAILs every
deployed copy fleet-wide.

## When to Use

- User asks to slim SOUL.md / AGENTS.md / a template to a byte target
- Doctor flags SOUL.md size WARN/FAIL and the fix is a real trim (not a re-baseline)
- Consolidating or merging template principles/sub-points
- Any doc whose propagation is governed by soul-merge.py or an audit regex gate

## Know What Each Enforcement Layer Counts — BEFORE Cutting

| Layer | What it counts | Wrong trim's consequence |
|-------|---------------|--------------------------|
| Doctor `_extract_soul_markers` | `- **` list bullets ONLY (Core Traits) | Consolidating trait bullets = permanent reverse-drift WARN on every deployed copy (soul-merge never removes them) |
| Doctor `check_soul_sync` | `### N. Title` principle headings (title-key matched) | Removing a canonical title = FAIL "missing canonical principles" |
| soul-merge `_find_missing_subpoints` | `**marker**` prefix anywhere in a principle body | Renaming/merging markers = OLD marker stays + NEW one added on deployed = duplication, not consolidation |
| agents-doc-audit | heading regexes (`^## Identity`, `^## Core Mission`, …) | Removing a heading = commit-gate FAIL |

**Safe to compress freely (proven 2026-08-19: SOUL template 14,737 → 10,032 B):**
- Preambles and continuation prose after bold markers — they only reach FRESH
  deploys; existing deployed copies keep their rich versions (add-only merge).
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
   deltas). Run `soul-merge.py --check` for idempotency.
5. **Deploy + verify** — copy to repo template, run `soul-merge.py` (updates
   deployed), run the doctor (`check_soul_sync` PASS, size ≤ WARN), run
   `agents-doc-audit.py --repo . --json` (missing sections == []).
6. **Commit + push** — pre-push hook requires deployed == repo checksum, so run
   `cortex-update.sh` BEFORE `git push` (doc changes: the enforcement chain is
   commit → deploy → push).

## Pitfalls

- **Consolidating trait bullets** seems like easy wins but permanently WARNs
  every deployed copy. Keep all `- **` bullet names; shorten only their prose.
- **Renaming a sub-point marker** duplicates content on deployed copies (old +
  new both present). Fold into the existing marker name instead.
- **Rewriting from memory** re-pastes identical bytes — always edit on-disk via
  programmatic replace and verify the byte delta.
- **Pushing before cortex-update** — pre-push hook fails "Checksum: AGENTS.md"
  when deployed != repo. Deploy first.
- **soul-merge.py only adds** — a leaner template does NOT shrink existing
  deployed copies; it only makes fresh deploys lean. If the deployed copy must
  shrink too, trim it directly (keeping marker parity).

## Verification

- `wc -c docs/templates/SOUL.md` ≤ target; deployed ≤ 15,360 (WARN) / 20,480 (FAIL)
- Doctor: `✅ SOUL.md template sync`, `✅ SOUL.md canonical 12`, `✅ SOUL.md
  reverse drift`, no FAILs
- `soul-merge.py --check` → exit 0 ("up to date")
- `agents-doc-audit.py --repo . --json` → `missing_sections: []`
- `git log --oneline -1 origin/main` shows the pushed commit
