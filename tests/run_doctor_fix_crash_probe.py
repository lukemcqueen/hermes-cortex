#!/usr/bin/env python3
"""The one-line demonstration of the crash the doctor's consumer scan used to raise.

`find_script_consumers()` used to iterate its roots and call `Path(root)` directly, so a caller
handing in a non-path entry crashed the whole check:

    TypeError: argument should be a str or an os.PathLike object where __fspath__ returns a
    str, not 'NoneType'

The fix skips such an entry. This script prints what the function does with `[None]` at whatever
revision it is run against, so the before/after is one command in each tree:

    cd /tmp/hc-base   && python3 tests/run_doctor_fix_crash_probe.py    # pre-fix: traceback, rc=1
    cd ~/hermes-cortex && python3 tests/run_doctor_fix_crash_probe.py   # fixed: empty result, rc=0

Exit 0 when the call is handled, 1 when it raises.
"""
import importlib.util
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dc_probe", REPO / "ops/scripts/manage/cortex_doctor/config.py")
assert _spec is not None and _spec.loader is not None
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)

print(f"revision under test: {REPO}")
try:
    out = dc.find_script_consumers([None])
except Exception:
    print("find_script_consumers([None]) RAISED:")
    traceback.print_exc(limit=1)
    sys.exit(1)

print(f"find_script_consumers([None]) returned: {out}")
print("RESULT: handled (no exception)")
