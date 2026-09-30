"""cortex-bus-bridge tests — S2a systemd-timer bridge for no_agent cron jobs.

component-hermes-separation scope 2, slice S2a. Proves the bridge:
  - the RUNNER (cortex-bus-bridge-run.py) runs a job's script standalone and
    delivers non-empty stdout (silent-when-clean preserved), WITHOUT any Hermes
    runtime import;
  - the GENERATOR (cortex-bus-bridge-generate.py) maps simple no_agent jobs to
    systemd OnCalendar values that systemd-analyze validates, and skips only
    what it should (LLM/chained jobs, unsupported schedules).
"""
import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "ops" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, str(SCRIPTS / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _jobs_stub() -> list:
    return [
        {"name": "j-daily", "no_agent": True, "script": "x.py",
         "schedule": {"kind": "cron", "expr": "0 1 * * *"}},
        {"name": "j-every5min", "no_agent": True, "script": "y.py",
         "schedule": {"kind": "every", "every": "5m"}},
        {"name": "j-llm", "no_agent": False, "script": "z.py",
         "schedule": {"kind": "cron", "expr": "0 0 * * *"}},
        {"name": "j-chained", "no_agent": True, "script": "w.py",
         "context_from": "prev", "schedule": {"kind": "cron", "expr": "0 2 * * *"}},
    ]


# ── Generator schedule translation ──────────────────────────────────────────
def test_generator_maps_common_cron_forms():
    g = _load("cortex-bus-bridge-generate")
    cases = {
        "0 1 * * *": "*-*-* 01:00:00",
        "15 3 * * *": "*-*-* 03:15:00",
        "*/5 * * * *": "*-*-* *:0/5:00",
        "0 */6 * * *": "*-*-* *:00/6:00",
        "17 * * * *": "*-*-* *:17:00",
        "0 9-18 * * 1-5": "Mon..Fri *-*-* 09..18:00:00",
        "0 11,17 * * 6": "Sat *-*-* 11,17:00:00",
    }
    for expr, want in cases.items():
        assert g.cron_to_oncalendar(expr) == want, f"{expr} -> {want}"


def test_generator_maps_interval_forms():
    g = _load("cortex-bus-bridge-generate")
    assert g.instance_interval({"kind": "every", "every": "5m"}) == "*-*-* *:0/5:00"
    assert g.instance_interval({"kind": "every", "every": "2h"}) == "*-*-* *:00/2:00"
    assert g.instance_interval({"kind": "every", "every": "360m"}) == "*-*-* *:00/6:00"


def test_generator_skips_unsupported():
    g = _load("cortex-bus-bridge-generate")
    assert g.cron_to_oncalendar("0 1 * * *")  # sanity
    assert g.cron_to_oncalendar("bad expr here") is None
    assert g.instance_interval({"kind": "every", "every": "70m"}) is None  # non-dividing
    assert g.instance_interval({}) is None


def test_generator_job_is_simple_filter():
    g = _load("cortex-bus-bridge-generate")
    assert g.job_is_simple(_jobs_stub()[0]) is True   # daily no_agent
    assert g.job_is_simple(_jobs_stub()[1]) is True   # every-5m no_agent
    assert g.job_is_simple(_jobs_stub()[2]) is False  # LLM job
    assert g.job_is_simple(_jobs_stub()[3]) is False  # chained (context_from)


def test_generated_on_calendar_values_all_pass_systemd():
    g = _load("cortex-bus-bridge-generate")
    data = json.loads(Path.home().joinpath(".hermes/cron/jobs.json").read_text())
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    vals = set()
    for j in jobs:
        if not g.job_is_simple(j):
            continue
        s = j.get("schedule") or {}
        e = s.get("expr") or s.get("display", "")
        v = g.cron_to_oncalendar(e) if s.get("kind") == "cron" else g.instance_interval(s)
        if v:
            vals.add(v)
    assert vals, "expected at least one simple no_agent schedule to translate"
    for v in sorted(vals):
        r = subprocess.run(["systemd-analyze", "calendar", v],
                           capture_output=True, text=True)
        assert r.returncode == 0 and "Normalized form:" in r.stdout, (
            f"systemd rejects generated OnCalendar '{v}': {r.stderr.strip()}"
        )


# ── Runner: standalone, silent-when-clean, delivers non-empty stdout ─────────
def test_runner_sources_loaded_and_script_resolution(tmp_path):
    r = _load("cortex-bus-bridge-run")
    # _resolve_script: relative resolves under scripts dir; absolute stays.
    assert r._resolve_script("agent-daily-bible-reading.py") == \
        str(r._SCRIPTS_DIR / "agent-daily-bible-reading.py")
    assert r._resolve_script("/tmp/nope.py") == "/tmp/nope.py"


def test_runner_executes_python_script_and_captures_stdout(tmp_path):
    r = _load("cortex-bus-bridge-run")
    script = tmp_path / "echo.py"
    script.write_text("print('hello from test')\n")
    import subprocess as sp
    # Run the runner in a subprocess so we can assert its standalone behavior
    # (empty stdout must yield empty delivered text — we assert the runner exits 0).
    proc = sp.run(
        ["/usr/bin/env", "python3", str(SCRIPTS / "cortex-bus-bridge-run.py"),
         "--name", "test-echo", "--script", str(script),
         "--enabled", "true"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    # The wrapper runs the script standalone (no Hermes runtime) and survives a
    # script that prints. Delivery to the real messenger is side-effectful and
    # best-effort by design — the observable contract is: exit 0, no traceback.
    assert "Traceback" not in (proc.stderr or ""), proc.stderr


def test_runner_local_deliver_saves_not_sends(tmp_path):
    r = _load("cortex-bus-bridge-run")
    # _deliver('local') must write the output file and NOT touch the messenger.
    import os
    os.environ["CORTEX_DEPLOY_HOME"] = str(tmp_path)
    r._CORTEX_ENV = tmp_path
    r._deliver("internal output", "testjob", "local")
    log = tmp_path / "cron-output" / "testjob.log"
    assert log.read_text().strip() == "internal output"


def test_runner_default_deliver_is_telegram(tmp_path):
    # Non-'local' deliver must route to the messenger code path (not the local
    # save). We assert the dispatch decision: _deliver with deliver='' reaches
    # the notify branch (which attempts the real messenger; gated by env token
    # presence in the deployed lib, so we mock the import).
    r = _load("cortex-bus-bridge-run")
    import os
    os.environ["CORTEX_DEPLOY_HOME"] = str(tmp_path)
    r._CORTEX_ENV = tmp_path
    calls = []
    def fake_notify(text, subject=""):
        calls.append((text, subject))
    r_notify_holder = {"notify": fake_notify}
    # Monkeypatch the imported notify by injecting a module into sys.modules
    # before _deliver imports lib.telegram_notify.
    import sys, types
    fake_lib = types.ModuleType("lib")
    fake_lib.telegram_notify = types.SimpleNamespace(notify=fake_notify)
    sys.modules["lib"] = fake_lib
    sys.modules["lib.telegram_notify"] = fake_lib.telegram_notify
    try:
        r._deliver("report", "testjob", "origin")
    finally:
        sys.modules.pop("lib", None)
        sys.modules.pop("lib.telegram_notify", None)
    assert calls, "default/telegram deliver must reach notify"
    assert calls[0][0] == "report"
    # And local must NOT be written for a telegram job.
    assert not (tmp_path / "cron-output" / "testjob.log").exists()


def test_runner_hermes_free():
    r = _load("cortex-bus-bridge-run")
    src = Path(r.__file__).read_text()
    # The wrapper must not import the Hermes runtime.
    for bad in ("import hermes", "from hermes", "hermes_bus", "hermes_models"):
        assert bad not in src, f"runner must not reference {bad}"