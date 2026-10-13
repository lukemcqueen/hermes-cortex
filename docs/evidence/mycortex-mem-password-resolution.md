# mycortex-mem password resolution — verification evidence

Date: 2026-10-08 (Titus host, macOS 14.8.7)

## Change
`resolve_mem_password()` added to `ops/services/mycortex-mem/store.py` and mirrored in
`plugins/mycortex-mem/__init__.py`. Resolution order: `os.environ["MYCORTEX_MEM_PASSWORD"]`
override first, else read the canonical `~/hermes-cortex/.env` (then `~/.hermes-cortex/.env`).
This makes the provider available in launchd/systemd gateway services that do NOT inherit
`~/hermes-cortex/.env`, WITHOUT any Hermes-specific service env injection (decoupled design).

## 1. Unit tests — 9/9 pass
Command: `python3 -m pytest tests/test_mycortex_mem_psql_no_password.py -v`

```
collected 9 items
tests/test_mycortex_mem_psql_no_password.py::test_store_macos_invocation_forbids_password_prompt PASSED
tests/test_mycortex_mem_psql_no_password.py::test_store_linux_invocation_forbids_password_prompt PASSED
tests/test_mycortex_mem_psql_no_password.py::test_plugin_macos_invocation_forbids_password_prompt PASSED
tests/test_mycortex_mem_psql_no_password.py::test_plugin_linux_invocation_forbids_password_prompt PASSED
tests/test_mycortex_mem_psql_no_password.py::test_resolve_mem_password_env_var_wins PASSED
tests/test_mycortex_mem_psql_no_password.py::test_resolve_mem_password_falls_back_to_cortex_env PASSED
tests/test_mycortex_mem_psql_no_password.py::test_resolve_mem_password_missing_env_returns_empty PASSED
tests/test_mycortex_mem_psql_no_password.py::test_store_macos_cmd_uses_resolved_password_in_pgpass PASSED
tests/test_mycortex_mem_psql_no_password.py::test_store_fails_fast_and_never_prompts_without_a_password PASSED
============================== 9 passed in 0.19s ===============================
```

The 4 new tests cover: env-var-wins, .env-fallback, missing→empty, and pgpass-uses-resolved-password.

## 2. Integration — store resolves password from .env and connects (no env var set)
Command: `env -u MYCORTEX_MEM_PASSWORD python3 ops/services/mycortex-mem/context_tools.py mem_context '{}'`

Returns live memory (peer card + facts), proving the store reads the password from
`~/hermes-cortex/.env` and authenticates. (Output truncated here; full card/facts returned.)

## 3. Host→container SCRAM auth works after role reconciliation
Command: `PGPASSWORD="$PW" psql -h 127.0.0.1 -p 15432 -U mycortex_mem_reader -d mycortex -w -t -A -c "SELECT 'host-scram-ok';"`

```
host-scram-ok
```

The `mycortex_mem_reader/writer/admin` roles' scram passwords were reconciled to the
`~/hermes-cortex/.env` `MYCORTEX_MEM_PASSWORD` value (they previously differed, which is why
the provider reported unavailable even with the resolver).

## 4. Deployed copies carry the resolver
- `~/.hermes-cortex/services/mycortex-mem/store.py` — `grep -c "def resolve_mem_password"` → 1
- `~/.hermes/plugins/mycortex-mem/__init__.py` — `grep -c "def resolve_mem_password"` → 1, and
  `_cmd()` calls `pw = resolve_mem_password()`.

## Remaining (orchestrator action)
Restart the gateway from a separate shell so it loads the patched plugin:
`launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway`, then `hermes memory status` → available.
