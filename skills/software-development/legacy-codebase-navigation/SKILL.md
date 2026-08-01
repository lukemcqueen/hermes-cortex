---
name: legacy-codebase-navigation
description: "Navigate, understand, and debug large legacy codebases (Rails, Django, early Node). Techniques for tracing data through deep helper chains, reading mutation-heavy code without getting lost, and finding the exact transformation that damaged your data."
version: 1.0.0
author: Hermes Cortex (troubleshooter)
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [legacy, rails, debugging, codebase-navigation, data-tracing]
    related_skills: [root-cause-debugging, project-map, codebase-design]
---

# Legacy Codebase Navigation

## Overview

Legacy codebases share common traits that make them harder to debug than greenfield projects:
- **Deep helper chains** — data passes through 5+ transformation layers (controller → helper → sub-helper → sub-sub-helper)
- **Mutation-heavy code** — `gsub!`, `gsub`, `strip`, `upcase` chained in long sequences, each step mutating state
- **Side-effect rich** — functions set instance variables, write logs, touch the DB as a side effect of "computation"

## Tracing Data Through Helper Chains

### 1. Build the call graph first

Find every link in the chain before touching code:

```bash
# In Rails: find the helper method and all its callers
grep -rn "def my_helper" app/helpers/
grep -rn "my_helper(" app/ --include="*.rb" | grep -v "def "

# In any codebase: who calls this method?
grep -rn "method_name(" . --include="*.rb" --include="*.py" --include="*.js" | grep -v "def "
```

### 2. Trace the data, not the code

Follow the **value** through each transformation. For each link in the chain,
write down: input → output. When the output is wrong, the transformation that
changed it is the bug.

```ruby
# Instead of reading this chain linearly:
title.gsub('(', ' - ').gsub(')', '').strip.upcase

# Ask: what does EACH step do to the value?
# 1. gsub('(', ' - ')   → "Artist (INST.)" → "Artist  - INST.)"
# 2. gsub(')', '')      → "Artist  - INST."
# 3. strip              → "Artist  - INST."
# 4. upcase             → "ARTIST  - INST."
```

### 3. Use the debugger at the boundary

Set a breakpoint at the entry and exit of the suspect helper — not inside
every line:

```bash
# Rails: binding.pry at the helper entry, print the input
# then step through only if the output looks wrong
```

## Reading Mutation-Heavy Code Without Getting Lost

- **Make a state table** — list every variable and its value at each step.
  Mutation chains are just state tables with the intermediate values hidden.
- **Distinguish computation from side effects** — a method that mutates an
  instance variable AND returns a value is doing two things; you must check both.
- **Look for the "last writer wins" pattern** — in long chains, the final
  mutation determines the result; earlier ones may be dead code or bugs.

## Finding the Exact Transformation That Damaged Data

When you know data is corrupted but not where:

1. **Identify the shape of the damage** — what does the bad data look like
   vs the good data? (Missing suffix? Wrong case? Duplicated text?)
2. **Search for transformations that could produce it**:
   ```bash
   grep -rn "gsub\|sub(\|strip\|upcase\|downcase\|tr(" app/helpers/ app/models/ | head -50
   ```
3. **Reproduce with the actual data** — feed a known-good sample through each
   candidate transformation in a console/REPL and compare outputs.
4. **Confirm with the DB** — find rows that match the damage pattern and rows
   that don't; the transformation must explain the difference.

## Pitfalls

- ❌ **Reading linearly** — helper chains are trees, not lists. Trace values.
- ❌ **Fixing the symptom** — the wrong output is produced 4 layers up; patching
  the display hides it. Fix the transformation.
- ❌ **Trusting method names** — `clean_title` may not clean anything. Read the body.
- ❌ **Ignoring side effects** — a "pure" helper that writes to the DB is
  anything but. Check for `update`, `save`, `create` in helpers.

## Related
- `root-cause-debugging` — the 6-phase debugging framework
- `project-map` — structural project analysis
- `codebase-design` — module vocabulary
- `rails-data-pipeline-debugging` — specific data-pipeline patterns in Rails
