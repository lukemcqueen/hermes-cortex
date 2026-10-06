# mycortex-mem psql — committed, re-runnable evidence

Regenerate with: `bash ops/services/mycortex-mem/run-evidence.sh`

Generated: 2026-10-06T04:31:09Z

Artifacts this evidence was produced from (verify with `sha256sum`):

```
f7eee0669c7a645ffb70225e1fb57d8903f924f0742a8fc387126130accd629e  ops/services/mycortex-mem/store.py
29faeb40372cd1ec229c91e95abe83a3278178847ef0df73434d0d672f8bf2cb  plugins/mycortex-mem/__init__.py
5bfadf8db1de2ac8720712f86f7d33c26bd6de48d5aeea9a0d5f679ce5236f70  tests/test_mycortex_mem_psql_no_password.py
0f45f5d192d5115865690eb023a3cabcafb004b4778c315c663d4212cc490670  ops/services/mycortex-mem/run-evidence.sh
```

## 1. Command composition + runtime fail-fast — PASS (exit 0)

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: $HOME/hermes-cortex
configfile: pytest.ini
plugins: anyio-4.12.1
collected 5 items

tests/test_mycortex_mem_psql_no_password.py .....                        [100%]

============================== 5 passed in 0.10s ===============================
```

## 2. RED case — the runtime test against a store WITHOUT `-w` must fail: FAIL (exit 1)

```

=================================== FAILURES ===================================
__________ test_store_fails_fast_and_never_prompts_without_a_password __________
tests/test_mycortex_mem_psql_no_password.py:166: in test_store_fails_fast_and_never_prompts_without_a_password
    assert "no password supplied" in str(excinfo.value), str(excinfo.value)
E   AssertionError: psql error: $HOME/.hermes/cache/scratch/pytest-of-esther/pytest-370/test_store_fails_fast_and_neve0/bin/psql: 8: cannot create /dev/tty: No such device or address
E   assert 'no password supplied' in 'psql error: $HOME/.hermes/cache/scratch/pytest-of-esther/pytest-370/test_store_fails_fast_and_neve0/bin/psql: 8: cannot create /dev/tty: No such device or address'
E    +  where 'psql error: $HOME/.hermes/cache/scratch/pytest-of-esther/pytest-370/test_store_fails_fast_and_neve0/bin/psql: 8: cannot create /dev/tty: No such device or address' = str(StoreUnavailable('psql error: $HOME/.hermes/cache/scratch/pytest-of-esther/pytest-370/test_store_fails_fast_and_neve0/bin/psql: 8: cannot create /dev/tty: No such device or address'))
E    +    where StoreUnavailable('psql error: $HOME/.hermes/cache/scratch/pytest-of-esther/pytest-370/test_store_fails_fast_and_neve0/bin/psql: 8: cannot create /dev/tty: No such device or address') = <ExceptionInfo StoreUnavailable('psql error: $HOME/.hermes/cache/scratch/pytest-of-esther/pytest-370/test_store_fails_fast_and_neve0/bin/psql: 8: cannot create /dev/tty: No such device or address') tblen=3>.value
=========================== short test summary info ============================
FAILED tests/test_mycortex_mem_psql_no_password.py::test_store_fails_fast_and_never_prompts_without_a_password
============================== 1 failed in 0.11s ===============================
```

Proves: `-w` is present at every invocation site, and with no usable password the
store raises `StoreUnavailable` promptly instead of waiting on an invisible prompt
(fail-open, no hang) — while a store lacking the flag is caught by the same test.

Does not prove: behaviour against a live password-requiring server reachable from
this host (none is); that check belongs on the harness host after deploy.
