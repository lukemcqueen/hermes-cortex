#!/usr/bin/env python3
"""Drive the INSTALLED hermes-jev plugin's own hook, in shadow mode, with no gateway.

The plugin only loads at gateway start, so a restart would be the usual way to find
out whether it works. This probe drives the real artifact instead: it imports the
installed module, injects the shadow switch in-process (the `/jev routing shadow`
switch normally lives in state.json — nothing live is written here), calls the real
`pre_llm_call` hook with a real coding turn, and reads back what the plugin decided
and what it logged.

HERMES_HOME is repointed at a scratch dir FIRST, so the plugin's own decision log is
written there and the live ~/.hermes/logs/jev-decisions.jsonl is untouched.
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

HERMES_HOME = pathlib.Path(os.environ.get("HERMES_HOME") or (pathlib.Path.home() / ".hermes"))
PLUGIN = str(HERMES_HOME / "plugins" / "hermes-jev" / "__init__.py")
SCRATCH_HOME = pathlib.Path(os.environ.get("JEV_PROBE_HOME")
                            or (pathlib.Path(tempfile.gettempdir()) / "jev-probe-home"))
SCRATCH_HOME.mkdir(parents=True, exist_ok=True)
os.environ["HERMES_HOME"] = str(SCRATCH_HOME)

PLUGIN_DIR = pathlib.Path(PLUGIN).parent
# The plugin imports its vendored kit RELATIVELY (`from .jevkit import ...`), so it has
# to load as a PACKAGE whose __path__ is its own directory — a bare file import dies
# with ModuleNotFoundError.
spec = importlib.util.spec_from_file_location(
    "hermes_jev_under_test", PLUGIN, submodule_search_locations=[str(PLUGIN_DIR)])
mod = importlib.util.module_from_spec(spec)
sys.modules["hermes_jev_under_test"] = mod
spec.loader.exec_module(mod)

TURN = ("the governance enforcer lock gate refuses a write outside any governed repo; "
        "add a narrow exemption for the knowledge brain and pin it with tests")

# Routing is applied by the `llm_request` MIDDLEWARE (register_middleware), not by
# pre_llm_call — the first probe drove the wrong seam and correctly saw nothing.
for mode in ("shadow", "on", "off"):
    settings = {"routing": mode, "skills": "off", "notice": "on", "merge_requests": "on"}
    mod._setting = lambda name, default, _s=settings: _s.get(name, default)
    mod._TURNS.clear()
    session = f"probe-{mode}"
    mod._on_pre_llm_call(session_id=session, turn_id=1, user_message=TURN)
    request = {"model": "deepseek/deepseek-v4.1-flash",
               "messages": [{"role": "user", "content": TURN}]}
    returned = mod._on_llm_request(request=dict(request), session_id=session, turn_id=1,
                                  model="deepseek/deepseek-v4.1-flash", provider="openrouter",
                                  base_url="https://openrouter.ai/api/v1")
    record = mod._TURNS.get(session) or {}
    decision = record.get("decision") or {}
    print(f"--- routing={mode} ---")
    print("  outgoing model IN  :", request["model"])
    print("  middleware returned:", json.dumps(returned, default=str)[:200] if returned else returned)
    print("  decision.routed    :", decision.get("routed"))
    print("  decision.mode      :", decision.get("mode"))
    print("  decision.model     :", decision.get("model"))
    print("  decision.tier      :", decision.get("tier"))
    print("  decision.reason    :", decision.get("reason"))
    print("  decision.latency_ms:", decision.get("latency_ms"))

log = SCRATCH_HOME / "logs" / "jev-decisions.jsonl"
print("\ndecision log:", log)
if log.exists():
    for line in log.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        print("  ", {k: row[k] for k in ("kind", "mode", "routed", "model", "tier", "latency_ms")
                     if k in row})
else:
    print("  NONE — the hook logged nothing")
