---
name: rails-data-pipeline-debugging
description: "Debugging data transformation bugs in legacy Rails apps — tracing heuristic text-splitting, internationalisation helpers, and CPLEX/CSV import pipelines."
version: 1.2.0
author: Hermes Cortex
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [rails, debugging, data-pipeline, legacy, text-processing, heuristics]
    related_skills: [root-cause-debugging, change-test-loop, codebase-design]
---

# Rails Data Pipeline Debugging

## Overview

Legacy Rails apps (especially music copyright / royalty systems with Korean/English i18n) rely heavily on heuristic-based helper methods to split text containing parentheses into language pairs. These heuristics silently corrupt data when a parenthetical suffix (e.g., `(INST.)`, `(MR)`, `(LIVE)`) is mistaken for a language translation.

This skill documents the pattern for tracing, diagnosing, and fixing these bugs.

## When to Use

- Song titles or artist names end up with missing suffixes (e.g., `(INST.)` dropped)
- Korean/English bilingual text gets split at the wrong parenthesis
- A data migration produced subtly wrong strings that "look mostly right"
- Debugging a CPLEX/CSV import that mangles certain rows
- Any heuristic text transformation in a legacy pipeline

## The Core Pattern: Heuristic Language-Pair Splitting

Legacy systems store bilingual titles like:

```
"사랑의 불시착 (Crash Landing on You)"
"Because I Love You (사랑하기 때문에)"
```

A heuristic `split_title` helper decides which side is Korean and which is
English, often by scanning for Hangul characters or paren positions:

```ruby
def split_title(title)
  if title.include?("(") && title.include?(")")
    # guess: content in parens is the translation
    main = title[/^(.*?)\(/].strip
    trans = title[/\((.*?)\)/].strip
    { main: main, translation: trans }
  else
    { main: title, translation: nil }
  end
end
```

### The Failure Mode

```
"Because I Love You (INST.)"  → main="Because I Love You", translation="INST."
```

`(INST.)` is NOT a translation — it's an instrumental suffix. The heuristic
corrupts the title. When the pipeline later reconstructs
`"#{main} (#{translation})"`, the title survives — but when it uses only
`main`, the suffix is lost forever. Data damage is silent and irreversible
without backups.

## Diagnostic Method

### 1. Find the exact transformation

```bash
# Find the splitter
grep -rn "def split_title\|def parse_title\|def extract_korean\|def extract_english" app/helpers/ app/models/ | head -10

# Find all callers — the damage may occur in one path only
grep -rn "split_title(" app/ --include="*.rb" | grep -v "def " | head -20
```

### 2. Reproduce with real data

```ruby
# In rails console — feed the actual damaged values
titles = ["Because I Love You (INST.)", "사랑 (Love)", "Love (LIVE)", "Not Bilingual"]
titles.each { |t| p [t, split_title(t)] }
```

### 3. Classify the damage pattern

Query the DB for rows matching the damage signature:

```ruby
# Titles whose main-part should have had a suffix
Title.where("title LIKE ?", "%(INST%)").count
Title.where("title LIKE ?", "%(LIVE%)").count
# Or: rows where translation column contains a non-language value
Title.where("translation IN (?)", %w[INST LIVE MR MIX VER REMIX])
```

### 4. Trace the write path

Which import/export path wrote the corrupted value?

```ruby
# Find where the split result is persisted
grep -rn "translation\|main_title\|\.main\b" app/services/ app/jobs/ app/models/ | grep -iE "save|update|create" | head -20
```

## Fix Patterns

### A. Whitelist the suffix set

If the splitter only handles `(...)` as translation, make it reject known
non-language suffixes:

```ruby
NON_LANGUAGE_PARENS = %w[INST LIVE MR MIX VER REMIX FEAT KARAOKE INSTRUMENTAL]

def split_title(title)
  return { main: title, translation: nil } unless title.include?("(")
  inner = title[/\((.*?)\)/, 1].to_s
  return { main: title, translation: nil } if NON_LANGUAGE_PARENS.include?(inner.upcase)
  # ... normal split
end
```

### B. Require language evidence

Only treat parens as translation if the content contains non-ASCII script
(Hangul, CJK, Cyrillic):

```ruby
def translation?(text)
  text.match?(/\p{Hangul}|\p{Han}|\p{Cyrillic}/)
end
```

### C. Fix the data, not just the code

The heuristic already corrupted stored rows. After fixing the code, run a
data repair migration:

```ruby
Title.where("translation IN (?)", %w[INST LIVE MR MIX VER REMIX]).find_each do |t|
  t.update!(title: "#{t.main} (#{t.translation})", translation: nil)
end
```

**Always back up first, and verify counts before/after.**

## CPLEX/CSV Import Pipeline Notes

CPLEX (copyright exchange) imports share the same failure class:

- A CSV column meant to hold `(translation)` gets a non-language value
- The import's normalizer strips or splits on parens
- Row-level errors are silently swallowed (rescued per-row with no logging)

```ruby
# Find silent per-row rescues — the sign of swallowed data damage
grep -rn "rescue.*=>\|rescue StandardError\|begin.*rescue" app/services/ app/jobs/ | grep -iE "import|csv|cplex" | head -10
```

Fix: log the row + error, count failures, fail loudly on systemic corruption.

## Pitfalls

- ❌ **Fixing only the display** — the stored data stays corrupt; fix the write path + repair the data
- ❌ **"Mostly right" assumptions** — verify with counts, not eyeballing
- ❌ **Silent per-row rescues** — they hide systemic corruption; log and surface
- ❌ **Assuming one splitter** — the app may have 3+ copies of the heuristic; grep broadly
- ❌ **Not backing up before repair** — a wrong repair migration is worse than the bug

## Verification

```ruby
# After the fix
titles = ["Because I Love You (INST.)", "사랑 (Love)", "Love (LIVE)"]
# Expect: INST/LIVE stay in main title, real translations still split
assert_equal "Because I Love You (INST.)", split_title("Because I Love You (INST.)")[:main]
assert_equal "Love", split_title("Love (LIVE)")[:main]
assert_equal "Crash Landing on You", split_title("사랑의 불시착 (Crash Landing on You)")[:translation]
```

```bash
# Run the regression tests
rails test test/helpers/title_splitter_test.rb
```

## Related
- `legacy-codebase-navigation` — tracing data through deep helper chains
- `root-cause-debugging` — 6-phase framework
- `change-test-loop` — small verified changes
- `local-cwr-file-processing` — CWR export/ACK validation (same domain)
