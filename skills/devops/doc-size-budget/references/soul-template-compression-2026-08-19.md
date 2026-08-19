# SOUL.md Compression Recipe (2026-08-19) — 14,737 B → 10,032 B

Session: Luke asked "reduce repetitive thinking costing money" → then "get SOUL
to 10k without losing effectiveness" → "your deployed can be closer to 15k if
you need" → "it's enough."

## Outcome

- `docs/templates/SOUL.md`: 14,737 → 10,032 B (−32%). All 12 canonical
  principles, 9 trait bullets, 15 sub-point markers (16th added), 7 mandatory
  sections, all audit regex anchors preserved.
- Deployed `~/.hermes/SOUL.md`: 16,835 → 15,112 B (under the 15,360 WARN gate)
  via soul-merge + direct trims (removed duplicate Jonah scripture entry, stale
  local-principles note, verbose old preambles).
- New canonical sub-point under P4 (Sabbath Tempo):
  `**No repetitive re-derivation**` — the actual money-saver: agents were
  re-stating the same conclusion 3× per task (Titus PYEONG/PYOUNG example).
- AGENTS.md rule 28: `**State it once, then move**`.
- Committed `3df083fc`, pushed, doctor HEALTHY (326 pass · 0 warn).

## Enforcement-layer mechanics (the critical knowledge)

1. **Doctor `_extract_soul_markers`** (cortex_doctor/checks.py) matches ONLY
   `^\s*-\s+\*\*([^*]+)\*\*` — `- **` list bullets. In SOUL.md that's the Core
   Traits section (9 bullets). Principle sub-points (`**Text** — ...` paragraphs
   without `- `) are NOT counted. → Consolidating trait bullets would create a
   permanent reverse-drift WARN on every deployed copy (soul-merge is add-only,
   old names never leave). Keep all 9 trait names; only shorten their prose.

2. **Doctor `check_soul_sync`** also title-matches `### N. Title` headings via
   `_soul_title_key`. Removing a canonical title = FAIL "missing canonical
   principles". Keep all 12 titles byte-identical.

3. **soul-merge.py `_find_missing_subpoints`** matches `**marker**` prefix
   anywhere in a principle body. Renaming/merging markers → OLD marker stays on
   deployed + NEW marker gets added = duplication. Fold redundant sub-points
   INTO an existing marker name, never a new name.

4. **agents-doc-audit.py SECTION_PATTERNS** — heading regexes (`^## Identity`,
   `^## Core Mission`, `^## Behavioral Principles`, `^## Communication Style`,
   `^## Scripture Insights`) + keyword regexes. Removing a heading = pre-commit
   gate FAIL.

## What was safe to cut

- Preamble prose of each principle (only reaches FRESH deploys; deployed copies
  keep rich versions via add-only merge).
- Continuation lines after bold markers (same reason).
- Merged "A manual workaround is not a fix" INTO "Test the actual send before
  remote surgery" (existing marker name; deployed copies already had it → no
  duplication).
- Scripture: removed 2 of 3 deployed entries (keep LAST as cron anchor).
- Deployed-only: removed stale `**Local principles (0-12, optional, your
  choice).**` block (old template variant, was nested inside P12 sub-points).

## The token-waste loop (why "WASTING MONEY!")

The agent repeatedly `write_file`'d the full file from memory while claiming to
compress — byte count stayed 11,560 across 6+ writes. Fix that worked:
Python script with a list of (old, new) replacement pairs applied to the
on-disk file with `str.replace`, counting `applied: n / total`, printing
per-section sizes, then `wc -c`. Byte count moved every run.

## Verification commands used

```bash
python3 - <<'EOF'  # invariants: titles, traits, markers, headings
import re
t = open('/tmp/soul-template-10k.md').read()
print(len(re.findall(r'^### \d+\. .+$', t, re.M)))          # 12
print(len(re.findall(r'^- \*\*([^*]+)\*\*', t, re.M)))      # 9 traits
print(len(re.findall(r'^\*\*([^*]+)\*\*', t, re.M)))        # markers
for s in ["## Identity","## Core Mission","## Core Traits",
          "## Communication Style","## Behavioral Principles",
          "## Scripture Insights","## Final Directive"]:
    assert s in t, s
EOF

python3 ops/scripts/manage/soul-merge.py --check   # exit 0 = idempotent
python3 ops/scripts/manage/cortex-doctor.py --quiet  # HEALTHY
python3 ops/scripts/agent/agents-doc-audit.py --repo . --json  # missing: []
bash ops/scripts/secret-leak-detector.sh           # clean
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <f> --level A2 --gate
```

## Push chain for doc changes (pre-push hook)

`git push` FAILED with "❌ Checksum: AGENTS.md" because deployed
`~/.hermes/AGENTS.md` hadn't been updated yet. The enforcement chain is:
commit → `cortex-update.sh` (deploys AGENTS.md + SOUL.md to ~/.hermes) →
push. Doctor was HEALTHY only AFTER cortex-update ran.

## Follow-ups left open

- Bus broadcast via `inbox_send(to='all')` failed HTTP 401 on all endpoints —
  same peer-ACL class as earlier sessions; commit+deploy propagates regardless.
- `doc-freshness` and `soul-refinement` skills are user-owned (created_by=None);
  recommend `hermes curator adopt` so background curation can patch them with
  the compression mechanics directly.
