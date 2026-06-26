# Profile Auth.json Inheritance

**DEPRECATED (June 2026):** Profile-per-project was abandoned. This file documents a problem that no longer applies with the current uber-agent + gbrain architecture. Kept for reference only.

## The Problem

When Hermes Agent starts with `--profile <name>` and the profile has no `auth.json`,
it falls back to root `~/.hermes/auth.json` — works fine.

**But** the first time Hermes is used with that profile, it auto-creates
`~/.hermes/profiles/<name>/auth.json` with an empty credential pool:

```json
{
  "version": 1,
  "providers": {},
  "credential_pool": {
    "opencode-zen": []
  }
}
```

This profile-scoped auth.json **takes precedence** over root. The empty credential pool
causes: *"It looks like Hermes isn't configured yet -- no API keys or providers found."*

## Symptoms

- `hermes --version` works fine (no provider needed)
- `hermes --profile <name>` fails with the "not configured" error
- Root `hermes` (no profile) works fine
- Profiles that never had an auto-created `auth.json` work fine

## Root Cause

Hermes looks for credentials in this order:

1. Profile-level `auth.json` (if exists)
2. Root `~/.hermes/auth.json`
3. Environment variables

If (1) exists but has empty `credential_pool`, Hermes does NOT proceed to (2).
The empty entry blocks the fallback.

## Fix

**One-shot:** Copy root auth to the affected profile:
```bash
cp ~/.hermes/auth.json ~/.hermes/profiles/<name>/auth.json
```

**All profiles:**
```bash
~/bin/sync-hermes-auth.sh
```

**Prevention:** `scripts/cortex-profile.sh` now includes step 2b that copies root
auth.json during profile creation.

## Caveat

If you later configure a custom provider for a specific profile (e.g., a different
API key for one project), Hermes will update that profile's auth.json. This may
overwrite the root creds if Merkle-merge isn't used. After adding per-profile
credentials, re-run `sync-hermes-auth.sh` to ensure root creds are still present
alongside the custom ones.
