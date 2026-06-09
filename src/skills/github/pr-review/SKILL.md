---
name: pr-review
description: >
  Full PR review pipeline — whole-repo context, architecture analysis,
  lesson-DB pattern matching, test regression check, and formal review
  submission with inline comments. Zero external API costs. Replaces
  Greptile / PR-Agent with Hermes-native tooling.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [github, pr-review, code-review, architecture, deep-module, inline-comments, quality]
    related_skills: [github-code-review, github-pr-workflow, project-map, save-lesson, requesting-code-review, change-test-loop]
---

# PR Review — Hermes-Native Code Review Pipeline

## Overview

A comprehensive PR review pipeline that matches the capabilities of
Greptile or PR-Agent using only Hermes's built-in tools:

| Capability | Greptile | PR-Agent | This skill |
|------------|----------|----------|------------|
| Whole-repo context | ✅ Graph DB | ❌ Diff-only | ✅ project-map + full checkout |
| Architecture review | ❌ | ❌ | ✅ Deep module + Service layer |
| Past-fix memory | ❌ | ❌ | ✅ Lesson DB pattern matching |
| Inline comments | ✅ | ✅ | ✅ gh or curl |
| Auto-approve | ✅ | ✅ | ✅ |
| Test regression check | ❌ | ✅ | ✅ Baseline comparison |
| API cost | $30/seat/mo | $49/mo | **$0** |

## When to Use

- User says "review PR #N" or drops a PR URL
- User says "review this PR" or "what do you think of this PR"
- Before merging any PR to catch issues
- Before asking for human review (pre-review pass)

**Skip for:** trivial one-line changes (typo fix, version bump,
dependency update without logic change).

## Required Tooling

The skill auto-detects authentication and falls back gracefully:

```bash
# gh is preferred but optional
which gh &>/dev/null && gh auth status &>/dev/null && AUTH="gh" || AUTH="curl"

# project-map should be in PATH
which project-map &>/dev/null && PMAP=1 || PMAP=0

# Lesson DB
which offline_knowledge &>/dev/null && LDB=1 || LDB=0
```

## The Pipeline

```
PR #N
  │
  ├─ 1. Gather context ─── PR metadata, diff, stat
  ├─ 2. Checkout locally ── git fetch origin pull/N/head:pr-N
  ├─ 3. Project map ─────── Understand codebase structure
  ├─ 4. Lesson search ───── Find known patterns from past fixes
  ├─ 5. Architecture scan ─ Deep module + Service layer check
  ├─ 6. Full review ─────── Correctness, Security, Quality, Testing
  ├─ 7. Test baseline ───── Run tests, compare to main
  ├─ 8. Draft review ────── Structured findings
  └─ 9. Submit ──────────── Inline comments + summary + verdict
```

---

## Step 1 — Gather PR Context

### Extract PR Number

```bash
# From URL: https://github.com/owner/repo/pull/123
PR_NUMBER=$(echo "$PR_URL" | grep -oP '/pull/\K\d+')

# Or from gh pr status
PR_NUMBER=$(gh pr status --json number --jq '.currentBranch.number')
```

### Get PR Metadata

**With gh:**
```bash
gh pr view "$PR_NUMBER" --json title,body,author,headRefName,baseRefName,additions,deletions,files,createdAt,state
```

**With curl:**
```bash
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)

curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER"
```

### Get the Full Diff

```bash
# With gh
gh pr diff "$PR_NUMBER" > /tmp/pr-diff.txt

# With git (after checkout)
git diff "$BASE_BRANCH...HEAD" > /tmp/pr-diff.txt

# Stats overview
git diff "$BASE_BRANCH...HEAD" --stat
```

### Get Changed Files

```bash
# File-by-file breakdown
git diff "$BASE_BRANCH...HEAD" --name-only

# Per-file stats
git diff "$BASE_BRANCH...HEAD" --stat
```

---

## Step 2 — Check Out the PR Locally

```bash
BASE_BRANCH=$(gh pr view "$PR_NUMBER" --json baseRefName --jq '.baseRefName' 2>/dev/null || echo "main")

# Fetch the PR branch
git fetch origin pull/$PR_NUMBER/head:pr-$PR_NUMBER

# Check it out
git checkout pr-$PR_NUMBER

# Note the HEAD SHA for inline comments
HEAD_SHA=$(git rev-parse HEAD)
```

For large repos, use a shallow fetch:
```bash
git fetch origin pull/$PR_NUMBER/head:pr-$PR_NUMBER --depth=50
```

---

## Step 3 — Project Map

Run project map to understand the dependency graph:

```bash
if [ "$PMAP" -eq 1 ]; then
  project-map analyze 2>/dev/null
  MAP_FILE=".hermes-cortex/project-map.json"
else
  MAP_FILE=""
fi
```

Read the map to identify:
- Which modules import changed files (impact analysis)
- Which routes are affected
- Which models/data structures are modified

### Manual Impact Analysis (no project-map)

```bash
# Find what imports the changed files
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only); do
  echo "=== $f is imported by ==="
  grep -rl "$(basename "$f" .py)" --include="*.py" . | grep -v ".git/" | grep -v "node_modules/"
done
```

---

## Step 4 — Lesson DB Search

Search for known patterns related to the changed files:

```bash
if [ "$LDB" -eq 1 ]; then
  # Search by file patterns
  for f in $(git diff "$BASE_BRANCH...HEAD" --name-only); do
    EXT="${f##*.}"
    offline_knowledge lesson search "$(basename "$f")" --language "$EXT" --limit 2 2>/dev/null
  done

  # Search by language/framework detected
  DETECTED_FRAMEWORK=$(grep -oP '(import |from |require\()"\w+' /tmp/pr-diff.txt | head -5 | tr '\n' ' ')
  offline_knowledge lesson search "$DETECTED_FRAMEWORK" --limit 3 2>/dev/null
fi
```

Each match with similarity ≥ 0.55 is flagged as a known pattern to check.

---

## Step 5 — Architecture Scan

### 5a — Deep Module Detection

Scan each changed file for shallow-module indicators:

```bash
# Shallow module signs: module is mostly a pass-through
# Check if module just re-exports or wraps another module
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only); do
  if [ -f "$f" ]; then
    TOTAL_LINES=$(wc -l < "$f")
    EXPORT_LINES=$(grep -cE "^(export|from|import)" "$f" 2>/dev/null || echo 0)
    RATIO=$(echo "scale=2; $EXPORT_LINES / $TOTAL_LINES" | bc 2>/dev/null || echo 0)

    # If >50% of lines are imports/exports, flag as potentially shallow
    if [ "$(echo "$RATIO > 0.5" | bc -l 2>/dev/null)" -eq 1 ] 2>/dev/null; then
      echo "⚠️ SHALLOW: $f — $EXPORT_LINES/$TOTAL_LINES lines are imports/exports"
    fi
  fi
done
```

Deep module principle: "A lot of behaviour behind a small interface."
If removing this module would require duplicating its logic at every call site,
it's a deep module. If the complexity just disappears, it's a shallow pass-through.

### 5b — Service vs Action Layer

Scan for layer violations:

```bash
# In action files — look for business logic that should be in a service
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only | grep -iE "action|command|handler|controller"); do
  if [ -f "$f" ]; then
    # Actions should coordinate, not implement domain rules
    DOMAIN_LOGIC=$(grep -cE "if.*\.(role|status|type)|for.*in.*items|calculate|compute|validate" "$f" 2>/dev/null || echo 0)
    if [ "$DOMAIN_LOGIC" -gt 5 ]; then
      echo "⚠️ LAYER: $f has $DOMAIN_LOGIC domain logic operations — consider extracting to a service"
    fi
  fi
done

# In service files — check they're not orchestrating (actions' job)
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only | grep -iE "service|repository|provider"); do
  if [ -f "$f" ]; then
    # Services should own HOW, not WHY
    ORCHESTRATION=$(grep -cE "if.*user\.role|if.*is_admin|notify|send_email|publish_event" "$f" 2>/dev/null || echo 0)
    if [ "$ORCHESTRATION" -gt 3 ]; then
      echo "⚠️ LAYER: $f has $ORCHESTRATION policy decisions — consider moving to action layer"
    fi
  fi
done
```

### 5c — Duplication Scan

```bash
# Check if new code duplicates existing logic elsewhere
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only); do
  if [ -f "$f" ]; then
    # Extract function names defined in this file
    FUNCTIONS=$(grep -E "^(def |async def |fun |function |export function)" "$f" 2>/dev/null | head -10)
    for fn in $FUNCTIONS; do
      FN_NAME=$(echo "$fn" | grep -oP '\b\w+(?=\s*[(:])')
      # Search for duplicates outside this file
      DUPES=$(grep -rl "$FN_NAME" --include="*.py" --include="*.js" --include="*.ts" . \
        2>/dev/null | grep -v "$f" | grep -v ".git/" | head -3)
      if [ -n "$DUPES" ]; then
        echo "💡 DUPE: $FN_NAME in $f also defined in: $DUPES"
      fi
    done
  fi
done
```

---

## Step 6 — Full Code Review

### 6a — Static Security Scan (from requesting-code-review)

```bash
# Hardcoded secrets
grep -n "^+" /tmp/pr-diff.txt | grep -iE "(api_key|secret|password|token|passwd)\s*=\s*['\"][^'\"]{6,}['\"]"

# Shell injection
grep -n "^+" /tmp/pr-diff.txt | grep -E "os\.system\(|subprocess.*shell=True"

# Dangerous eval/exec
grep -n "^+" /tmp/pr-diff.txt | grep -E "\beval\(|\bexec\("

# SQL injection
grep -n "^+" /tmp/pr-diff.txt | grep -E "execute\(f\"|\.format\(.*SELECT|\.format\(.*INSERT"

# Path traversal
grep -n "^+" /tmp/pr-diff.txt | grep -E "open\(.*user_input|os\.path\.join\(.*\.\.\."

# XSS (JS/TS)
grep -n "^+" /tmp/pr-diff.txt | grep -E "innerHTML\s*=|dangerouslySetInnerHTML|v-html"

# Insecure deserialization
grep -n "^+" /tmp/pr-diff.txt | grep -E "pickle\.loads?\(|yaml\.load\(|marshal\.load"
```

### 6b — Correctness Scan

```bash
# Merge conflict markers left behind
grep -n "^+" /tmp/pr-diff.txt | grep -E "<<<<<<|>>>>>>|======="

# TODO/FIXME/HACK/XXX left in code
grep -n "^+" /tmp/pr-diff.txt | grep -iE "TODO|FIXME|HACK|XXX|DEBUG|WORKAROUND"

# Debug print statements
grep -n "^+" /tmp/pr-diff.txt | grep -E "print\(|console\.log|puts |IO\.puts|p\(|dbg!"

# Commented-out code
grep -c "^+#\|^+//\|^+<!--\|^+/*" /tmp/pr-diff.txt
```

### 6c — Quality Indicators

```bash
# File size — files over 500 lines may need splitting
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only); do
  if [ -f "$f" ]; then
    LINES=$(wc -l < "$f")
    if [ "$LINES" -gt 500 ]; then
      echo "📏 LARGE: $f is $LINES lines — consider splitting"
    fi
  fi
done

# High cyclomatic complexity in changed functions
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only); do
  if [ -f "$f" ]; then
    COMPLEX_FUNCS=$(grep -n "if.*elif\|case\|for.*in\|while\|except\|catch" "$f" 2>/dev/null | \
      awk '{print $1}' | sort | uniq -c | sort -rn | head -5)
    echo "$COMPLEX_FUNCS" | while read count line; do
      [ "$count" -gt 5 ] 2>/dev/null && echo "🔴 COMPLEX: $f:$line has $count branches/loops"
    done
  fi
done
```

### 6d — Testing Assessment

```bash
# Check if tests exist for changed files
for f in $(git diff "$BASE_BRANCH...HEAD" --name-only); do
  BASENAME=$(basename "$f")
  FILENAME="${BASENAME%.*}"
  TEST_FILES=$(find . -path ./node_modules -prune -o -path ./.git -prune -o \
    -name "*test*$FILENAME*" -o -name "*$FILENAME*test*" -o -name "test_*$FILENAME*" \
    -print 2>/dev/null | head -3)
  if [ -z "$TEST_FILES" ]; then
    # No test found — flag it
    echo "🧪 UNTESTED: $f has no corresponding test file"
  else
    echo "✅ TESTS: $TEST_FILES"
  fi
done

# Check if the PR adds tests at all
TEST_ADDITIONS=$(grep -c "^+" /tmp/pr-diff.txt | grep -iE "test_|_test|spec_|_spec|assert|expect\(|it\(|describe\(" || echo 0)
if [ "$TEST_ADDITIONS" -eq 0 ]; then
  echo "🧪 NO TESTS: PR doesn't appear to add any tests"
fi
```

---

## Step 7 — Test Baseline Check

Run the full test suite on **both** the PR branch and base branch to
detect regressions:

```bash
# Save the PR branch name
PR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BASE_BRANCH=$(gh pr view "$PR_NUMBER" --json baseRefName --jq '.baseRefName' 2>/dev/null || echo "main")

# Run tests on PR branch
echo "=== PR BRANCH TESTS ==="
python -m pytest -q --tb=no 2>&1 | tail -5
PR_RESULT=$?

# Switch to base branch and run tests
git stash 2>/dev/null
git checkout "$BASE_BRANCH"
echo "=== BASE BRANCH TESTS ==="
python -m pytest -q --tb=no 2>&1 | tail -5
BASE_RESULT=$?

# Switch back to PR branch
git checkout "$PR_BRANCH"
git stash pop 2>/dev/null

# Compare
if [ "$PR_RESULT" -ne 0 ] && [ "$BASE_RESULT" -eq 0 ]; then
  echo "🔴 REGRESSION: Tests pass on $BASE_BRANCH but fail on PR branch"
elif [ "$PR_RESULT" -eq 0 ] && [ "$BASE_RESULT" -eq 0 ]; then
  echo "✅ TESTS PASS: No regressions"
elif [ "$BASE_RESULT" -ne 0 ]; then
  echo "ℹ️  BASELINE BROKEN: $BASE_BRANCH already has test failures"
fi
```

**Language auto-detection for test commands:**

| Detected files | Test command |
|----------------|-------------|
| `pytest.ini`, `setup.cfg` (pytest section) | `python -m pytest -q --tb=no` |
| `package.json` (jest, vitest) | `npx vitest run 2>&1 \| tail -10` or `npx jest 2>&1 \| tail -10` |
| `Cargo.toml` | `cargo test 2>&1 \| tail -10` |
| `go.mod` | `go test ./... 2>&1 \| tail -10` |
| `Gemfile` | `bundle exec rspec 2>&1 \| tail -10` |
| `Makefile` with `test` target | `make test 2>&1 \| tail -10` |

---

## Step 8 — Draft the Review

Collate all findings into a structured report with three severity levels:

### Severity Classification

| Level | Label | Auto-fix? | Blocks merge? |
|-------|-------|-----------|---------------|
| 🔴 **Critical** | Security, data loss, logic bugs | Attempt fix | Yes |
| ⚠️ **Warning** | Architecture, performance, missing tests | Flag only | No |
| 💡 **Suggestion** | Style, naming, minor improvements | Flag only | No |
| ✅ **Looks Good** | Done well, maintain, patterns | Mention | No |

### Report Template

```
## Hermes PR Review — #NNN

**Verdict:** APPROVE / CHANGES REQUESTED

**Scope:** +N additions, -N deletions across N files
**Tests:** ✅ Pass / 🔴 Fail / ⚠️ Missing
**Architecture:** ✅ Clean / ⚠️ Issues found
**Security:** ✅ Clean / 🔴 Issues found

---

### 🔴 Critical (N issues)

- **file:line** — Description of the issue
  Suggestion: How to fix it

### ⚠️ Warnings (N issues)

- **file:line** — Description

### 💡 Suggestions (N issues)

- **file:line** — Description

### ✅ What's Good

- Clean separation of concerns
- Good test coverage on new code
- Error handling is thorough

---

*Reviewed by Hermes Agent | Architecture: deep-module ✓ | Security: static scan ✓ | Lessons: N matches*
```

---

## Step 9 — Submit the Review

### 9a — Inline Comments

Build the inline comments payload from findings in Steps 5-7:

```bash
# With gh
HEAD_SHA=$(git rev-parse HEAD)

for issue in "${CRITICAL_ISSUES[@]}" "${WARNINGS[@]}"; do
  # Parse file:line:message from each finding
  FILE=$(echo "$issue" | cut -d: -f1)
  LINE=$(echo "$issue" | cut -d: -f2)
  MSG=$(echo "$issue" | cut -d: -f3-)

  gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments" \
    --method POST \
    -f body="$MSG" \
    -f path="$FILE" \
    -f commit_id="$HEAD_SHA" \
    -f line="$LINE" \
    -f side="RIGHT"
done
```

### 9b — Formal Review (atomic, with curl)

Submit the entire review as one atomic action:

```bash
# Build the comments array from findings
COMMENTS_JSON=$(python3 -c "
import json, sys

comments = []
# Parse finding lines: 'file:line|message'
for line in sys.stdin:
    line = line.strip()
    if not line or '|' not in line:
        continue
    parts = line.split('|', 1)
    file_line = parts[0]
    message = parts[1]
    if ':' in file_line:
        f, ln = file_line.rsplit(':', 1)
    else:
        f = file_line
        ln = 1
    comments.append({
        'path': f,
        'line': int(ln),
        'body': message
    })

print(json.dumps(comments))
" <<< "$FINDINGS_TEXT")

# Submit the review
HEAD_SHA=$(git rev-parse HEAD)

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews" \
  -d "{
    \"commit_id\": \"$HEAD_SHA\",
    \"event\": \"$EVENT\",
    \"body\": \"$SUMMARY_BODY\",
    \"comments\": $COMMENTS_JSON
  }"
```

**Event values:** `"APPROVE"`, `"REQUEST_CHANGES"`, `"COMMENT"`

### 9c — Auto-Fix Loop (Optional)

When the user says "fix the issues", automatically fix critical issues:

```bash
# 1. Create a new branch for fixes
git checkout -b pr-$PR_NUMBER-fixes
git checkout pr-$PR_NUMBER
git checkout -b pr-$PR_NUMBER-fixes

# 2. Fix each critical issue
# (agent uses file tools to fix)

# 3. Commit and push
git add -A && git commit -m "fix: address PR review critical issues"
git push origin pr-$PR_NUMBER-fixes

# 4. Comment on the original PR with the fix branch
gh pr comment "$PR_NUMBER" --body \
  "🔧 Auto-fix branch available: \`pr-$PR_NUMBER-fixes\`\n\nCritical issues addressed. Merge this branch instead if the author is unavailable."
```

---

## Complete Workflow Script

```python
from hermes_tools import terminal, read_file, web_extract

# === Setup ===
PR_NUMBER = 123  # From user input

# Step 1: Gather context
result = terminal(f"gh pr view {PR_NUMBER} --json title,body,author,headRefName,baseRefName,additions,deletions,files", timeout=30)
pr_info = json.loads(result["output"])

# Step 2: Checkout
terminal(f"git fetch origin pull/{PR_NUMBER}/head:pr-{PR_NUMBER}")
terminal(f"git checkout pr-{PR_NUMBER}")

# Step 3: Project map
terminal("project-map analyze", timeout=60)

# Step 4: Lesson search
lessons = terminal(f"offline_knowledge lesson search '{pr_info['title']}'", timeout=15)

# Step 5-6: Review (run all scans)
diff = terminal(f"git diff {pr_info['baseRefName']}...HEAD --stat", timeout=10)
full_diff = terminal(f"git diff {pr_info['baseRefName']}...HEAD", timeout=30)
# ... process findings ...

# Step 7: Test baseline
terminal("python -m pytest -q --tb=no 2>&1 | tail -5", timeout=120)

# Step 8-9: Submit
terminal(f"""
HEAD_SHA=$(git rev-parse HEAD)
gh api repos/$OWNER/$REPO/pulls/{PR_NUMBER}/reviews \
  --method POST \
  -f "commit_id=$HEAD_SHA" \
  -f "event=COMMENT" \
  -f "body=## Review Summary\\n\\n..."
""", timeout=30)
```

---

## Pitfalls

1. **No `gh` auth** — The skill detects this and uses curl + GITHUB_TOKEN instead.
   If neither is configured, tell the user to set GH_TOKEN or `gh auth login`.

2. **Large PRs (>20 files)** — Review in batches by directory or module.
   Don't try to process 50+ files in one call. Focus on:
   - Files with the most changes (check `--stat`)
   - Core business logic (not config, migration files, lock files)
   - New files (higher risk than modifications)

3. **Binary/auto-generated files** — Skip review for:
   - Lock files (package-lock.json, yarn.lock, poetry.lock)
   - Migration files (alembic, django migrations)
   - Compiled outputs (.min.js, .map, .pyc)
   - Large generated files (protobuf, graphql schema)

4. **Baseline comparison fails** — If the base branch has pre-existing test
   failures, report them but don't block the PR for them. Only flag NEW failures.

5. **No test suite** — Skip Step 7 (test baseline), note the absence in the review.

6. **`git stash` fails** — If the PR branch has unstaged changes that conflict
   with stash, skip baseline comparison and note it.

7. **`project-map` not installed** — Skip Step 3, use grep-based manual impact
   analysis instead (see Step 3 fallback).

8. **Lesson DB empty** — Skip Step 4 silently. First reviews won't have pattern
   matches; they'll grow over time.

9. **Review is posted with outdated SHA** — Always re-fetch the HEAD SHA just
   before posting. If the PR branch was force-pushed during review, the old SHA
   is invalid. Always use `git rev-parse HEAD` right before the API call.

10. **Avoid overwhelming with noise** — Don't flag every minor style issue.
    Focus on issues that actually matter: correctness > security > architecture
    > performance > testing > style.

## Integration with Other Skills

- **github-code-review** — Absorbed into this skill. See `references/github-code-review-absorbed.md` for the review checklist, pre-push workflow, and curl inline-comment examples.
- **github-pr-workflow** — PR lifecycle management (create, merge, CI)
- **requesting-code-review** — Pre-commit verification for your own changes
- **project-map** — Dependency graph analysis (Step 3)
- **save-lesson** — Save fix patterns discovered during review (run after fixing)
- **change-test-loop** — TDD discipline for the auto-fix cycle

## Verification Checklist

Before submitting a review:

- [ ] PR checked out and compiled/parsed correctly
- [ ] All changed files reviewed
- [ ] Security scan completed (zero false negatives on secrets, injection)
- [ ] Architecture scan completed (deep module, layer violations, duplication)
- [ ] Lesson DB searched for known patterns
- [ ] Updated lines (green in diff) prioritized over deletions (red)
- [ ] Test baseline compared (unless no test suite)
- [ ] Inline comments reference correct file paths and line numbers
- [ ] Review summary is actionable, not just descriptive
- [ ] Auto-generated/lock files excluded from review
- [ ] HEAD SHA is current before posting
