---
name: shared-config-convergence
description: "Use when adding deploy guards that protect runtime config."
version: 1.0.0
category: devops
author: Moses
license: MIT
platforms: [linux, macos]
---

# Shared Config Convergence — Guard Flags Must Reach Every Host

**Class of task:** adding, reading, or verifying a guard that stops a shared deploy script (`cortex-update.sh`, installer, convergence block) from overwriting runtime config (model, fallback providers, keys) that operators set per-host.

## The core rule

**An opt-out flag that lives in a gitignored per-host file only protects the host that hand-set it.**

The guard *code* ships to the fleet (it's in the committed script), but the flag *value* does not — `.env`, `~/.hermes-cortex/.env`, and similar are gitignored and never propagate. Every sibling host runs the unset-flag branch (the default = convergence runs), so their config gets overwritten to repo canonical while the author's host is the only one spared. A green check on the author's host is a **false green** — it proves the guard works only where the flag happens to be set.

## Decide the guard polarity before shipping

| Polarity | Code shape | Fleet effect |
|---|---|---|
| **Opt-`in` to converge** (recommended) | `if [[ -n "${FLAG:-}" ]]; then <converge>; fi` — converge ONLY when explicitly requested | Safe by default; no host converges unless someone opts in |
| **Opt-out of converge** | `if [[ -z "${FLAG:-}" ]]; then <converge>; fi` — converge unless a flag says stop | Dangerous: every host converges unless each one individually sets the flag |

If you keep an opt-out guard, the flag must be **pushed to every host** through the fleet-update/dispatch path at the same commit — never rely on each operator hand-adding it to their own gitignored `.env`.

## A SKIP flag is NOT the fix — operator-owned config should never be written

The polarity table above still assumes convergence *should* run under some flag. When the config key is genuinely **operator-owned** (model.default, fallback_providers — the runtime a human or per-host tooling sets), the correct fix is to **remove the convergence block entirely** so the shared deploy script NEVER writes that key on any host. Gating a write behind a flag — even an opt-in flag — leaves the overwriting code alive, ready to run the moment someone sets the var or a sibling misconfigures it. "Operator-owned, must not write" in a comment means nothing while the write still executes by default.

Removing the block is the durable fix and it needs no flag at all:

```bash
# BEFORE: guarded write still runs on flag-less hosts
if [[ -z "${CORTEX_SKIP_MODEL_CONVERGENCE:-}" && -f ".../install-model-default.sh" ]]; then
  bash ".../install-model-default.sh" ...
fi

# AFTER: block deleted — script never writes operator-owned config
# (keep the register() line so the helper stays deployed for MANUAL use)
```

A SKIP flag is a symptom-level patch: it works on the author's host, does nothing for the fleet, and leaves a footgun behind. Pair removal with a regression test asserting the deploy script references the config-writer only on its register (deployment) line, never as an invocation.

After removing the block, verify the DEPLOYED copy (not just the repo source) no longer carries the invocation — `cortex-update.sh`'s checksum gate and the doctor compare deployed vs repo, and an earlier deploy can leave the old auto-run alive until the next `cortex-update.sh` run. Confirm the operator-owned key is untouched across an actual deploy: snapshot `model.default` + `fallback_providers` before and after running cortex-update, and diff — unchanged proves the block is really gone from the executing path.

## Verify on a sibling, not your own host

Before claiming a convergence guard works, confirm the unset-flag branch on a host that does NOT have the flag (or read the code's default branch directly):

```bash
# Where is the flag read from?
grep -n "FLAG_NAME" ops/scripts/*.sh
# Is that file gitignored (per-host only)?
git check-ignore <that-file> && echo "per-host only — will NOT reach fleet"
```

If the flag file is gitignored and you set it only locally, expect every other host to take the converge path.

## Pitfalls

- Setting a flag in your own gitignored `.env` and declaring the guard "done" — the fleet gets the code but not the opt-out; siblings get clobbered and the user only finds out when they ask why *other* agents changed.
- Assuming a convergence-block skip that fired on your host means it fires everywhere. The `[[ -z ... ]]` default is the branch every flag-less host runs.
