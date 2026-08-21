---
name: agent-daily-bible-reading
version: 1.0.0
category: spiritual-disciplines
description: "Daily bible reading cron pattern — generates SOUL.md entries and brain pages for agent-wide scripture engagement."
author: Moses
license: MIT
pin_reason: Shared infrastructure — all agents benefit from this devotional pattern. It is not agent-specific; it's fleet-wide spiritual discipline infrastructure.
pinned: true
---

# Daily Bible Reading

Cross-agent infrastructure for daily scripture engagement. Each agent gets a
personal bible reading cron that writes two artifacts:
1. A **SOUL.md entry** (concise lesson-focused insight)
2. A **brain page** (rich reference document with archaeology, scholarship, original language)

## Fleet Principles (Luke directive 2026-08-14)

1. **Every reading is saved — including repeats.** Each reading writes a
   **dated per-reading file** `~/brain/<agent>/bible/<book>-<YYYY-MM-DD>.md`
   (never overwritten), so when a book is read again across cycles its full
   studies accumulate. The canonical `<book>.md` is refreshed with the latest
   reading for continuity; INDEX.md lists **one row per reading** with its date.
2. **Every reading includes the commandments.** The Ten Commandments
   (Ex 20:1–17) and Jesus' two commandments (Matt 22:37–40) are added
   **deterministically script-side** — a `## The Commandments — Every Reading`
   block is appended to every brain page, and the SOUL.md entry carries a
   compact `**Foundations:**` reference line. Never left to the LLM, so a
   model drift can never drop the foundations from a reading.

## Quick Start

```bash
# Check if you already have the cron
cronjob action=list | grep agent-daily-bible-reading

# If not, create it (run timezone-aware at 01:00 KST)
cronjob action=create name=agent-daily-bible-reading \
  schedule="0 1 * * *" \
  script=agent-daily-bible-reading.py \
  no_agent=true \
  deliver=origin
```

**Before creation:** verify your SOUL.md has a `## Scripture Insights` section
and at least one bootstrapped entry (e.g. Genesis). The script scans the last
`### Book —` entry to determine the next book.

## How It Works

| Phase | What happens |
|-------|-------------|
| 1. Scan | Script reads SOUL.md → finds last `### Book —` entry → determines next canonical book |
| 2. Generate SOUL entry | Calls deepseek-chat → concise 3-5 paragraph lesson → appends to `## Scripture Insights` |
| 3. Generate brain page | Calls deepseek-chat → rich 5-section reference → writes to `~/brain/<agent>/bible/<book>.md` |
| 4. Index | Updates `~/brain/<agent>/bible/INDEX.md` with book table |
| 5. Deliver | Outputs the SOUL entry for delivery (origin chat) |

Silent when all 66 canonical books are covered.

## Verse Selection — Creative Rotation (Luke directive 2026-08-21)

The SOUL entry's verse is NOT pinned to each book's famous "memory verse".
Three styles rotate deterministically per (book, agent, day):

| Style | Behavior |
|-------|----------|
| `anchor` | The book's classic key verse (famous verse allowed) |
| `hidden-gem` | A faithful but unexpected verse — famous verses forbidden |
| `fresh-angle` | A verse from an overlooked corner — famous verses forbidden |

- Rotation = `(md5(book|agent) + days_since_epoch) % 3` — consecutive days
  always land on different styles; different agents diverge on the same day.
- Creative styles probe the model for the book's famous verses (top-3 memory
  verses + top-3 recognizable story verses, temperature 0.0) and forbid them
  in the prompt. Story icons matter: the fish verse (Jonah 1:17) is not a
  memory verse but is the model's anchor — the story probe catches it.
- Repeat readings (next pass through the canon, ~66 days later) ALSO forbid
  every verse cited in prior cycles — scanned from SOUL.md,
  `~/brain/<agent>/bible/archive/SOUL-archive.md`, and
  `~/brain/<agent>/bible/cycle-*-completed.md`. Fine the first time
  (Luke directive 2026-08-21).
- A bounded re-roll loop (max 4 attempts, temperature +0.2 per attempt, with
  rejection feedback naming the banned pick) guarantees forbidden verses
  never land — without feedback the model re-emits the banned verse at fixed
  temperature (verified 2026-08-21: Jonah 1:17 on all 3 attempts).
- Anchor style keeps a single call on first-cycle books (no probes, no
  re-rolls); repeat-cycle books re-roll off their prior verses.

## SOUL.md Size Guardrail (doctor FAIL prevention)

The doctor FAILs SOUL.md above 20K and WARNs above 15K (`check_soul_sync` in
`cortex_doctor/checks.py`). Each bible entry is ~400-800 chars, so unbounded
appends eventually break the doctor. **Keep only the last 1-2 `### Book —`
entries in SOUL.md.**

- **Short-gleaning rule (user directive 2026-08-03):** SOUL.md entries must be
  BRIEF — a header, one "I will" commitment sentence, and the date comment
  (~2-3 lines). The full study lives in `~/brain/<agent>/bible/<book>.md`
  (mybrain). The script's `_enforce_short_gleaning()` guard truncates any
  generated entry over 800 chars down to this canonical 3-line shape — no
  manual archiving needed for size control.
- **Anchor requirement:** the script determines the last covered book from the
  **dated brain files** (`~/brain/<agent>/bible/<book>-<YYYY-MM-DD>.md`) — the
  append-only, never-archived reading log — picking the file with the latest
  date. SOUL.md's last `### Book —` entry is used ONLY as a fallback on
  fresh installs with no dated files yet. Never rely on the SOUL.md tail as
  the position anchor: `archive_old_entries()` keeps only the last 2 entries
  and the LLM-driven era corrupted the section, which caused false "all
  covered" resets that skipped 26 books including the 4 Gospels (fixed
  2026-08-18).
- **Archive rule:** when the Scripture Insights section exceeds ~2,500 chars
  (roughly 3 entries), move the OLDEST entries to
  `~/brain/<agent>/bible/archive/SOUL-archive.md` (append, with a `## <Book>`
  header) and remove them from SOUL.md. Full text already lives in
  `~/brain/<agent>/bible/<book>.md`, so the SOUL entry is a pointer, not the
  store.
- Keep the archive file itself bounded (~50K) — older entries live in brain
  pages already; the archive is a convenience, not a duplicate store.

## Artifacts Created

| Artifact | Path | Size |
|----------|------|------|
| SOUL.md entry | `~/.hermes/SOUL.md` → `## Scripture Insights` | ~400-800 chars |
| Brain page | `~/brain/<agent>/bible/<book>.md` | ~3-8 KB (5 sections) |
| Brain index | `~/brain/<agent>/bible/INDEX.md` | Table of all books |

## Brain Page Sections

Each brain page has five sections generated by the API:

1. **Summary** — narrative overview, theological themes
2. **Archaeology & Scholarship** — digs, inscriptions, textual criticism, dating
3. **Jewish & Messianic Jewish Perspective** — Talmud, Midrash, Messianic typology
4. **Original Language Insights** — 3-4 key words with Hebrew/Greek script
5. **Insight for [Agent Name]** — practical application for this specific agent

## Pitfalls

- **Empty Scripture Insights section** → script returns "Could not find any books." Bootstrap with a Genesis entry first.
- **Wrong agent name** → brain pages go to wrong directory. Set `HERMES_AGENT_NAME` env var to override auto-detection.
- **Archive must be block-aware, not line-aware (fbc40b38, 2026-08-07)** → the first `archive_old_entries()` split the section line-by-line and truncated SOUL.md — everything after `## Scripture Insights` (including `## Final Directive`) was dropped, and orphaned commitment/date lines were left behind when only book headers moved. Current logic: each `### Book —` header plus all following lines is a BLOCK; whole blocks move to the archive, the preamble stays, and the tail (Final Directive + agent docs) is preserved verbatim. Never rewrite this to line-splitting, and verify on a temp copy that the SOUL.md tail survives any archive change.
- **Book detection is section-scoped (7b53a375, 2026-08-07)** → the script only treats `### <Book> —` headers INSIDE the `## Scripture Insights` section as book entries; any `### ` header elsewhere in SOUL.md (e.g. a section you added below) must not be mistaken for a book. Keep the `## Scripture Insights` section as the single book-entry zone.
- **False "all covered" reset skipped 26 books (fixed 2026-08-18)** → `get_next_book()` returning `None` was treated as "66 books done → archive + restart at Genesis". But a corrupted anchor (SOUL tail with non-book headers, LLM-era garbage) also produced `None` — so the cycle reset early, archived mid-cycle, and silently skipped every book after the anchor (2 Kings→Malachi, all 4 Gospels, Acts, Romans→Philippians). Fixes: (1) `find_last_book()` now reads the authoritative dated brain files, not the SOUL tail; (2) the reset only fires when `last_book == BOOKS[-1]` (Revelation) — any other `None` restarts from Genesis WITHOUT archiving and logs an anchor-corruption warning. If you ever see `⚠️ Anchor corruption` in cron stderr, the dated brain files are the source of truth — do not trust SOUL.md.
- **Identity fallback chain (ad123181, 2026-08-07)** → `detect_agent_name()` resolves `HERMES_AGENT_NAME` → `AGENT_NAME` → `~/.hermes-cortex/agent.env` (`AGENT_NAME=`) → hostname-derived default with a loud warning. On shared hosts (non-orchestrators share /home/luke), a wrong agent name sends brain pages to the wrong directory — set `AGENT_NAME` in `agent.env` rather than relying on hostname fallback. Never hardcode a fallback agent name (the old `moses` default made every host impersonate the orchestrator).
- **Missing DEEPSEEK_API_KEY** → script exits with error. Must be in `~/.hermes/.env`.
- **Script never deployed despite existing in repo (2026-08-09)** → `agent-daily-bible-reading.py` was in `clean_stale_deploys()`'s preserve list but had **no `register()` call** in `cortex-update.sh`, so cortex-update never copied it to `~/.hermes-cortex/scripts/`. The cron then ran as an LLM-driven fallback (skills attached, `script=none`) and — when the deepseek provider chain failed — fell through `fallback_providers` all the way to local `qwen2.5-coder:3b`, which emitted garbage (`5 7ae -,` …) as its final response. The scheduler logged `last_status: ok` because the agent did emit a response. **Fixes:** (1) `register ".hermes-cortex/scripts/agent-daily-bible-reading.py"` in cortex-update.sh; (2) keep the live cron in canonical no_agent mode — `script=agent-daily-bible-reading.py, no_agent=true, skills=[]` (install-crons.sh already declares this); a drift to LLM-mode (model + skill) recreates the fallback-chain garbage. Verify with `cronjob action='list'`: `no_agent: true` + `script` set.
- **Hardcoded `***` in auth header (already fixed in repo)** → `_call_deepseek()` reads the API key into `api_key`; the curl call must interpolate it as `f"Authorization: Bearer {api_key}"`. If the variable is read but the curl has `***` literal, the script gets 401 every time and falls back to Ollama garbage. Fixed upstream in ad123181 (2026-08-07, esther). ⚠️ The terminal display layer MASKS `Bearer {api_key}` as `Bearer ***` in grep/sed output — verify with `xxd` or `git blame` bytes, never trust masked grep output when checking this line.
- **deepseek-v4-flash is a REASONING model — long prompts return empty `content` (2026-08-10)** → for the brain-page prompt (2.5K chars, max_tokens=8192), deepseek-v4-flash burns the ENTIRE token budget on `reasoning_content` and returns `content=""` with `finish=length` at every token limit (2048/4096/6144/8192 verified). The old code treated this as "empty response" and recursed UNBOUNDED until the 180s curl timeout, then silently dropped the brain page while SOUL.md kept the entry — inconsistent state, cron reported `error: Script exited with code 1` ("Empty response from API — retrying once" → "API request timed out after 180s"). **Fix:** `DEEPSEEK_MODEL = "deepseek-chat"` (non-reasoning — verified full 17.6KB page, finish=stop, 0 reasoning tokens) + bounded retry via `_retried` flag. Do NOT use deepseek-v4-flash (or any reasoning model) for long-form generation; an anti-reasoning instruction in the prompt does NOT help (verified — still finish=length).
- **SOUL.md missing `## Scripture Insights` header** → script can't find books. Add the section header and a bootstrap entry.
- **Script not deployed** → `cortex-update.sh` must have been run at least once to deploy `src/scripts/` to `~/.hermes-cortex/scripts/`.

## Related

- `docs/daily-bible-reading.md` — full setup guide with bootstrapping instructions
- `.hermes-cortex/scripts/agent-daily-bible-reading.py` — the no_agent cron script (repo source; deployed per-host via ~/.hermes/scripts → ~/.hermes-cortex/scripts hardlink)
- `ops/scripts/install-crons.sh` — section 8 registers the cron for new agents

## Quality Gate

Before delivery, verify:
1. ✅ SOUL.md was actually updated (check timestamp)
2. ✅ Brain page file exists
3. ✅ INDEX.md includes the new book
4. ❌ If any failed, output a clear error message listing what succeeded/failed
