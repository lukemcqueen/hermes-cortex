# Post-Merge Bugfix: Python 3.9 + Missing MAP Entry (2026-06-17)

## Context

After merging 8 new commits into `~/Developer/AI/hermes-cortex` (HEAD `7641f867`),
`cortex-update.sh --force-all` was run. Three bugs emerged:

## Bug 1: Missing platform_utils.py in Deployment Map

**Symptom:** `service-recovery` cron crashed on every tick:
```
ModuleNotFoundError: No module named 'platform_utils'
```

**Root cause:** `platform_utils.py` was added to `src/scripts/` in the new commits
but never registered in `cortex-update.sh`'s `register()` MAP. The file existed in
the repo but wasn't copied to `~/.hermes/scripts/`.

**Fix:** Added `register "src/scripts/platform_utils.py"` to `cortex-update.sh`
and manually `cp`'d the file.

## Bug 2: Python 3.9 Type-Hint Incompatibility

**Symptom:** After the file was copied, `service-recovery` still crashed:
```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

**Root cause:** Both `platform_utils.py` and `service-recovery.py` used Python
3.10+ PEP 604 union syntax (`str | None`, `list | None`, `int | float`).
macOS defaults to Python 3.9 which cannot parse this syntax.

**Files affected:**
- `platform_utils.py` — `str | None`, `list[str]`, `tuple[str, str, int]`
- `service-recovery.py` — `list | None`, `str | None`

**Fix:** Stripped all PEP 604 union type annotations from both files. Simple
return-type annotations were removed entirely (not replaced with
`Optional[str]` — just removed the `-> ...` part). For internal annotations,
`Optional`/`Union` from `typing` would be used if needed.

## Bug 3: Function Ordering Error

**Symptom:** After fixing type hints, `service-recovery` still crashed:
```
NameError: name '_check_scripts' is not defined
```

**Root cause:** `_check_scripts()` was referenced in `SERVICES = [...]` dict literal
at line 61, but the function wasn't defined until line 71. Python evaluates
module-level list/dict literals at import time — no hoisting.

**Fix:** Moved `_check_scripts()` definition (and `_make_service()`) ABOVE the
`SERVICES` list, and moved the `_last_restart` dict initialization between them.

## Verification

```bash
$ python3 ~/.hermes/scripts/service-recovery.py
$ echo $?
0  # Silent exit — all services healthy, no errors
```

## Upstream Changes Needed

1. `cortex-update.sh` — register `platform_utils.py` in MAP (done)
2. `platform_utils.py` — use `Optional[str]` instead of `str | None` (done)
3. `service-recovery.py` — strip PEP 604 union + fix function ordering (done)
4. Process: run `py39-check.sh` on all .py scripts before merging
