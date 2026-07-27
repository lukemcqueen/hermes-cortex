# Creating New vs Extending Existing — Decision Guide

## The Problem

Every agent defaults to "create new" when "update existing" is faster, safer, 
and doesn't fragment the codebase. This is the most expensive mistake in multi-file
systems — each new file is a debt that compounds.

## The Rule

**Before creating any new script, skill, cron, config, mechanism, or message type:**

1. Search with **3+ different terms** — one term never finds everything
2. `skills_list(<category>)` for the domain — load every matching skill
3. Check if the existing system can be **extended or wired** instead of replaced
4. If the capability exists but isn't wired, **wire it** — don't rebuild it

## Heuristic

If you're about to name a new file, pause. Could it be:
- A new function in an existing file?
- A new config key in an existing config?
- A new cron parameter instead of a new cron script?
- A new `register()` line in `cortex-update.sh` instead of a new script?

## Anti-Patterns

| Mistake | Correct Approach |
|---------|-----------------|
| Searching once with one term, concluding "nothing exists" | Search 3+ different patterns across files, content, and git history |
| Creating a parallel system when extending `cortex-update.sh`'s `register()` lines would work | Extend the existing deploy mechanism |
| Building a one-off test file instead of running inline tests | Run tests in the terminal — don't create permanent files for ephemeral checks |
| Creating a new CLI tool when an existing one can absorb the feature | Check if the feature fits as a new command in an existing CLI (e.g., `hc.py`) |
