---
name: subagent-delegation
description: "Use when pinning subagent models or multi-role reviews."
version: 1.1.0
category: devops
platforms: [linux, macos]
---

# Subagent Delegation

**Trigger:** "run the party on <model>", "pin subagents to <model>", "Cannot
resolve delegation provider", elicit / architecture-party via subagents,
multi-role design review.

## Pinning the subagent model

Delegation resolution order: `delegation.base_url` (direct endpoint) →
`delegation.provider` (named keychain bundle) → parent provider (inherit).
`delegation.model` applies on every branch.

**To pin subagents to a model on a direct endpoint**, set all three and leave
`provider` empty:

```yaml
delegation:
  model: <model-id>
  provider: ""          # empty — the direct endpoint takes precedence
  base_url: <openai-compatible-base>
  api_key: <key>        # read from the provider's env var, not auth.json
```

**Pitfall — the named-provider branch ignores env keys.** Setting
`delegation.provider: <named>` fails with "not logged into <name> Portal" even
when the matching `<NAME>_API_KEY` env var is exported. The named branch
resolves a credential bundle from `~/.hermes/auth.json` `credential_pool` only
(commonly just deepseek / opencode-zen / openrouter); it never reads the env
var. Fix: use the direct-endpoint form above.

**Secret-safe write:** `hermes config set delegation.model <id>` is fine for
non-secret fields, but set `delegation.api_key` via a Python yaml script
(`yaml.safe_load` → set key → `yaml.safe_dump`) so the key never lands in shell
history or logs. `write_file`/`patch` refuse `config.yaml` (security-sensitive).

**Nous inference API (verified):** base `https://inference-api.nousresearch.com/v1`,
key from `NOUS_API_KEY`; Fable model ids `anthropic/claude-fable-5`,
`anthropic/claude-fable-5.1`, `anthropic/claude-fable-latest`. List models:
`curl -H "Authorization: Bearer $NOUS_API_KEY" <base>/models`.

## Running a multi-role review as parallel subagents

When an elicit / architecture-party asks for a panel of roles, run them as
parallel `delegate_task` subagents — not sequential self-prompting:

1. **Write one design brief first** — the single source of truth every role
   reads (plus existing research docs).
2. **Two waves, not one.** Design roles first (Elicit, Architect,
   Domain/DevEx) writing to `docs/party/<role>.md`; then critique roles
   (Security, SRE, Product, QA) pointed at those files. Critics must critique
   the actual design, not a strawman re-derivation of it.
3. **File-per-role, summary-only return.** Each child writes its full section
   to its file and returns a one-paragraph summary; the parent synthesizes the
   weighted matrix / recommendation itself — never delegate the synthesis.
4. **Pass exact read paths + output path** in each child's context; children
   know nothing of the parent conversation.

## Delegating implementation (children that commit code)

When subagents will implement AND `git commit` (not just write review files),
three extra rules apply:

- **One subagent per git repository.** The git index is shared state — two
  parallel subagents in the SAME repo collide on `git add`/`git commit` even
  when they touch different files (staging serializes the whole working tree).
  Parallelize ACROSS repos; within one repo run subagents sequentially, or have
  them do the work without committing and commit serially yourself.
- **Put the full governance sequence in the child's context.** In a governed
  repo (Hermes Cortex enforcer), a child's first write blocks until it loads the
  always-skills and holds a lock. Tell it explicitly: load the 7 always-skills
  in one turn → `cache_search` → `begin_change` → work with TDD →
  `feedback_accept` → `end_change`, commit through the hooks (no `--no-verify`),
  and DO NOT `git push` — the parent reviews and pushes.
- **Verify the child's self-report with real tool output — never trust it.**
  "N tests pass" is a claim, not a fact. After it returns: `git log` for the
  commits, run the test suite yourself, read the key diffs. Catch what a weak
  model misses — a script that violates a repo naming convention (the doctor
  flags it), a graceful-SKIP that is actually an unverified check, a decision the
  child made because a slice left it open.
