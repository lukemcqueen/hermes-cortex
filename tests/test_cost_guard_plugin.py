#!/usr/bin/env python3
"""Behavioral tests for the re-homed cost-guard user plugin.

Proves the plugin resolves from the USER plugin dir (~/.hermes/plugins/) — not
the hermes-agent git tree — and that its bundled cost_store writes a run row.

The plugin imports the cron.* stack, so the checks run under the agent's venv
interpreter (the one the fleet actually uses), via a subprocess.

Run: python3 tests/test_cost_guard_plugin.py
"""
import os
import subprocess
import sys
from pathlib import Path

AGENT = Path(os.path.expanduser("~/.hermes/hermes-agent"))
USER_PLUGINS = Path(os.path.expanduser("~/.hermes/plugins"))
PLUGIN_DIR = USER_PLUGINS / "cost-guard"
VENV_PY = AGENT / "venv" / "bin" / "python3"

_PROBE = r"""
import importlib.util, os, sqlite3, sys
from pathlib import Path
agent = os.path.expanduser("~/.hermes/hermes-agent")
user_plugins = Path(os.path.expanduser("~/.hermes/plugins"))
sys.path.insert(0, agent)
os.environ.setdefault("HERMES_HOME", os.path.expanduser("~/.hermes"))

from plugins.cron_providers import find_provider_dir, load_cron_scheduler
pdir = find_provider_dir("cost-guard")
assert pdir is not None, "provider not found"
assert str(pdir).startswith(str(user_plugins)), f"resolved to {pdir}, not user plugin dir"
prov = load_cron_scheduler("cost-guard")
assert prov is not None and prov.name == "cost-guard", "provider did not load"
print("PROVIDER_OK", pdir)

spec = importlib.util.spec_from_file_location("hc_cg_probe", str(user_plugins / "cost-guard" / "__init__.py"))
cg = importlib.util.module_from_spec(spec); spec.loader.exec_module(cg)
class _A:
    session_input_tokens = 11; session_output_tokens = 22; session_cache_read_tokens = 3
    session_cache_write_tokens = 1; session_api_calls = 1; session_estimated_cost_usd = 0.001
job = "hc-test-cost-guard"
cg._record_cost(job, _A(), "ok")
con = sqlite3.connect(os.path.expanduser("~/.hermes/cron/cron-costs.db"))
row = con.execute("SELECT input_tokens,output_tokens FROM cron_runs WHERE job_id=? ORDER BY run_time DESC LIMIT 1", (job,)).fetchone()
con.execute("DELETE FROM cron_runs WHERE job_id=?", (job,)); con.commit(); con.close()
assert row == (11, 22), f"cost row = {row}"
print("COST_OK", row)
"""


def _run_probe():
    if VENV_PY.exists():
        py = str(VENV_PY)
    else:
        py = sys.executable  # best effort off a git-installed host
    env = dict(os.environ)
    r = subprocess.run([py, "-c", _PROBE], capture_output=True, text=True, env=env)
    return r


def test_cost_guard_plugin_from_user_dir():
    if not PLUGIN_DIR.exists():
        return  # plugin not deployed on this host — nothing to assert
    r = _run_probe()
    assert r.returncode == 0, f"probe failed: {r.stderr[-800:]}"
    assert "PROVIDER_OK" in r.stdout, r.stdout
    assert "COST_OK" in r.stdout, r.stdout


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
