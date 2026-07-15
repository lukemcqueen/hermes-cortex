---
name: commit-message
version: 1.0.0
category: github
description: >
  Write clear, structured git commit messages following Conventional Commits
  format. Includes type prefixes, scope, breaking change markers, and body
  conventions for automated changelog generation.
tags: [git, commit, conventional-commits, changelog]
related_skills: [github-pr-workflow, public-contribution]
---

# Commit Message Conventions

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type

| Type | When to use |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only changes |
| `style` | Formatting, linting — no code change |
| `refactor` | Code change that neither fixes nor adds |
| `perf` | Performance improvement |
| `test` | Adding or fixing tests |
| `chore` | Build, deps, tooling — no production code change |
| `ci` | CI config or script changes |
| `revert` | Reverting a previous commit |

### Scope (optional)

The area of the codebase affected:

- `cron`, `docs`, `api`, `ui`, `db`, `auth`, `deploy`, `skill`, `script`
- Use lowercase, hyphens for multi-word: `cron-job`, `fleet-ref`

### Subject

- Imperative mood: "Add" not "Added" or "Adds"
- No trailing period
- Max 72 characters — this is what appears in `git log --oneline`
- Lowercase after type/scope: `feat: add login` not `feat: Add login`

### Body (optional)

- Explain WHAT changed and WHY, not HOW
- Separate from subject with blank line
- Wrap at 72 characters
- Use bullet points for multiple reasons

### Footer (optional)

- Breaking changes: `BREAKING CHANGE: <description>`
- Issue references: `Closes #123`, `Refs #456`
- Co-authors: `Co-authored-by: Name <email>`

## Examples

```
feat(auth): add OAuth2 login with Google provider

Users can now sign in with their Google account.
Existing email/password auth is unchanged.

Closes #234
```

```
fix(api): handle empty request body in POST /users

The endpoint returned 500 when called with an empty body.
Now returns 400 with a descriptive error message.

Refs #345
```

```
refactor(cron): extract schedule validation to shared module

The same schedule parsing logic was duplicated across
install-crons.sh and the cron MCP tool. Moved to a shared
validate_schedule() function.

BREAKING CHANGE: schedule validation now rejects whitespace
in cron expressions. Existing schedules verified clean.
```

```
docs: add API authentication section to README

Documents how to obtain and use bearer tokens,
including example curl commands for each auth flow.
```

```
chore(deps): upgrade pandas to 2.2.0

Pins pandas >=2.2 to avoid the DataFrame.copy() regression
in 2.1.x. All tests pass.
```

## Rules for This Repo

- Always use lowercase type prefixes.
- Prefer `feat` or `fix` — save `refactor` for truly structural changes.
- Include scope for changes that affect a specific subsystem.
- One logical change per commit — don't combine `feat` + `fix` + `docs`.
- Use `git commit -m` for single-line commits, `git commit` (editor) for
  multi-line.
- For squashed PR merges: the merge commit message should be a summary
  of all commits in the branch, with `Co-authored-by` for contributors.

## Verification

```bash
# Check subject line length
git log -1 --pretty=%s | wc -c
# Should output ≤ 73 (72 + newline)

# Check for conventional commit format
echo "$(git log -1 --pretty=%s)" | grep -qE '^(feat|fix|docs|style|refactor|perf|test|chore|ci|revert)(\(.+\))?: '
# Exit 0 = valid format
```
