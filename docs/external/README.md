# docs/external/ — Everything Outside the Repo

**Convention added 2026-08-24 (Dexter Horthy: "Record anything that lives
outside the repo but that an agent needs to know exists (env var names,
payment setup, test accounts, third-party dashboards) in `docs/external/`.
Files on disk are free context — every future session starts smarter.")**

This directory records WHAT exists outside the repo and WHERE it lives —
**never VALUES**. Secrets and values stay in the gitignored env files.
An agent reading these files learns what's available without hunting or
asking; it reads the value from env when it needs it.

## Hard rule

- **NAMES only.** Never write a value, token, URL-with-credentials, or
  test account here.
- If a value would be needed, cite the env var name and the file that
  holds it (`~/.hermes-cortex/.env` or `~/.hermes/.env`, both gitignored).
- The PII gate enforces this — server URLs, domains, and personal
  identifiers are blocked from the public repo.

## Files

- [env-vars.md](env-vars.md) — the env var NAME registry (both env files)
- [external-services.md](external-services.md) — third-party services and
  where their credentials live
