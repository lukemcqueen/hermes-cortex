#!/usr/bin/env python3
"""Render the REAL routing notice from the INSTALLED plugin, driven by state.json.

Answers one question with the artifact itself rather than a claim: when Jev switches the
model, what exactly appears at the end of the reply, and does the `notice` switch in
state.json actually control it?

Nothing live is touched: HERMES_HOME is repointed at a scratch dir before the plugin is
imported, so `_home()` resolves the scratch state.json and the decision log is written
there. The real `_setting` is used — NOT monkeypatched — because "state.json drives it"
is the thing under test.
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

LIVE_HOME = pathlib.Path(os.environ.get("JEV_LIVE_HOME") or (pathlib.Path.home() / ".hermes"))
SCRATCH = pathlib.Path(os.environ.get("JEV_PROBE_HOME")
                       or (pathlib.Path(tempfile.gettempdir()) / "jev-notice-probe"))
SCRATCH.mkdir(parents=True, exist_ok=True)
(SCRATCH / "jev").mkdir(parents=True, exist_ok=True)
os.environ["HERMES_HOME"] = str(SCRATCH)

PLUGIN = LIVE_HOME / "plugins" / "hermes-jev" / "__init__.py"
if not PLUGIN.exists():
    sys.exit(f"plugin not installed at {PLUGIN}")

# The plugin imports its vendored kit RELATIVELY, so it must load as a package.
spec = importlib.util.spec_from_file_location(
    "hermes_jev_notice_probe", PLUGIN, submodule_search_locations=[str(PLUGIN.parent)])
mod = importlib.util.module_from_spec(spec)
sys.modules["hermes_jev_notice_probe"] = mod
spec.loader.exec_module(mod)

# A kept decision renders NO notice by design, so a demonstration needs a prompt Jev will
# actually route away from the current model. The trivial one should fall to `simple`.
PROMPTS = [
    ("trivial", "what is 2+2? just the number, nothing else"),
    ("coding", ("refactor the governance enforcer lock gate so every refusal path stays "
                "identical, then pin it with tests")),
]


# The tiers live in <home>/jev/routing.json, so the scratch home needs a copy or every
# decision reads "no tiers configured" and keeps the model. Copied, never written through.
LIVE_ROUTING = LIVE_HOME / "jev" / "routing.json"
if LIVE_ROUTING.exists():
    (SCRATCH / "jev" / "routing.json").write_text(LIVE_ROUTING.read_text(encoding="utf-8"),
                                                  encoding="utf-8")


def state(routing: str, notice: str) -> None:
    (SCRATCH / "jev" / "state.json").write_text(
        json.dumps({"routing": routing, "notice": notice}, indent=2) + "\n", encoding="utf-8")


def one_turn(session: str, prompt: str, notice: str) -> tuple:
    """Drive the real decision path and render the real notice for one turn."""
    state("on", notice)
    mod._TURNS.clear()
    mod._on_pre_llm_call(session_id=session, turn_id=1, user_message=prompt)
    mod._on_llm_request(request={"model": "deepseek/deepseek-v4.1-flash",
                                 "messages": [{"role": "user", "content": prompt}]},
                        session_id=session, turn_id=1,
                        model="deepseek/deepseek-v4.1-flash", provider="openrouter",
                        base_url="https://openrouter.ai/api/v1")
    decision = (mod._TURNS.get(session) or {}).get("decision") or {}
    rendered = mod._on_transform_output(response_text="Here is the change you asked for.",
                                        session_id=session)
    return decision, (rendered or "Here is the change you asked for.")


print(f"plugin   : {PLUGIN}")
print(f"scratch  : {SCRATCH}  (HERMES_HOME repointed; live state and log untouched)\n")

switched = 0
for label, prompt in PROMPTS:
    for notice in ("on", "off"):
        decision, rendered = one_turn(f"s-{label}-{notice}", prompt, notice)
        tail = rendered.splitlines()[-1]
        is_notice = tail.startswith("[Jev]")
        switched += bool(is_notice)
        print(f"--- prompt={label} notice={notice} ---")
        print(f"  answers : {json.dumps((mod._TURNS.get(f's-{label}-{notice}') or {}).get('route_answers'), default=str)[:300]}")
        print(f"  decision: routed={decision.get('routed')} tier={decision.get('tier')} "
              f"specialty={decision.get('specialty')} model={decision.get('model')} "
              f"confidence={decision.get('confidence')}")
        print(f"  reply ends with: {tail!r}")
        print()

print("=== the notice string the plugin itself composed (last switching turn) ===")
for label, prompt in PROMPTS:
    decision, _ = one_turn(f"s-{label}-final", prompt, "on")
    if decision.get("routed") and decision.get("notice"):
        print(" ", decision["notice"])
        break
else:
    print("  none of these prompts switched the model; the notice is switch-only by design")
print("\n=== decision log (scratch) ===")
log = SCRATCH / "logs" / "jev-decisions.jsonl"
for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else []):
    row = json.loads(line)
    if row.get("kind") == "route":
        print("  route:", {k: row[k] for k in ("routed", "tier", "specialty", "confidence",
                                               "difficulty", "reason", "policy") if k in row})
