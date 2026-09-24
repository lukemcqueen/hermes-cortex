"""Push-metrics sink deploy gate + template ownership (2026-09-23).

Regression this guards: the push CLIENT (`agent-push-metrics`) is a UNIVERSAL
cron — every host, every 5m — while the SINK (nginx xx005 reverse proxy in front
of VictoriaMetrics) was bundled with grafana/bus behind an opt-in flag that
defaulted OFF. Remote agents' pushes were refused 1053 consecutive runs, each
failure feeding the escalation loop (sensor → P1 issue → task reopen → cycle).

The gate must:
  - deploy the sink wherever a local VictoriaMetrics backend answers, with no
    config at all (the default has to work)
  - still honour an explicit HERMES_SERVICES, including one that excludes it
  - never let two templates own the same port (the block was SPLIT out of
    orch-hermes-services.conf, not duplicated)
  - be mirrored in install-nginx-full.sh (the other deploy path) — a gate in
    one deployer and not the other is the half-wired bug this test exists for
"""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NGINX_DIR = REPO / "ops" / "install" / "deploy" / "nginx"
APPLY = NGINX_DIR / "hermes-services-apply.py"
INSTALL_SH = NGINX_DIR / "install-nginx-full.sh"
SINK_CONF = NGINX_DIR / "metrics-sink.conf"
EXTRAS_CONF = NGINX_DIR / "orch-hermes-services.conf"


def _load_apply():
    spec = importlib.util.spec_from_file_location("hermes_services_apply_under_test", APPLY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_unset_with_local_backend_deploys_sink():
    decide = _load_apply().metrics_sink_decision
    deploy, why = decide(None, True)
    assert deploy is True, "the default (HERMES_SERVICES unset) must deploy where a sink exists"
    assert "auto-detect" in why


def test_default_unset_without_backend_does_not_deploy():
    decide = _load_apply().metrics_sink_decision
    deploy, why = decide(None, False)
    assert deploy is False, "no backend → no dead listener"
    assert "no local" in why


def test_explicit_all_deploys_even_without_backend():
    deploy, why = _load_apply().metrics_sink_decision("all", False)
    assert deploy is True, "explicit 'all' is an operator instruction, not a guess"
    assert "explicit" in why


def test_explicit_metrics_deploys():
    deploy, _ = _load_apply().metrics_sink_decision("bus,metrics", False)
    assert deploy is True


def test_explicit_module_match_is_case_insensitive():
    deploy, _ = _load_apply().metrics_sink_decision("Bus,Metrics", False)
    assert deploy is True


def test_explicit_list_without_metrics_wins_over_the_default():
    """An operator who spelled out the list did not ask for the sink."""
    deploy, why = _load_apply().metrics_sink_decision("dashboard,langfuse,health", True)
    assert deploy is False, "explicit config must beat the auto-detect default"
    assert "excluded" in why


def test_sink_template_exists_and_listens_on_xx005():
    text = SINK_CONF.read_text()
    assert "listen 13005 ssl;" in text, "port literal 13xxx is what the port-prefix translator rewrites per host"
    assert "__SSL_CERT__" in text and "__HTPASSWD_FILE__" in text
    assert "block_direct_ip" in text, "every app block keeps the direct-IP blocker"


def test_sink_block_has_exactly_one_owner():
    """The xx005 block must live in ONE template — a leftover copy would give
    nginx two server blocks for the same port after the split."""
    owners = [
        p.name for p in NGINX_DIR.glob("*.conf")
        if "listen 13005" in p.read_text() or "upstream metrics_backend" in p.read_text()
    ]
    assert owners == ["metrics-sink.conf"], f"xx005 owned by {owners}"


def test_extras_conf_no_longer_owns_metrics():
    text = EXTRAS_CONF.read_text()
    assert "13005" not in text
    assert "metrics_backend" not in text


def test_both_deploy_paths_gate_the_sink():
    """hermes-services-apply.py and install-nginx-full.sh must agree, or a host
    gets the sink or not depending on which deployer ran last."""
    sh = INSTALL_SH.read_text()
    assert "metrics-sink.conf" in sh, "install-nginx-full.sh must deploy the sink template"
    assert "CORTEX_VM_HEALTH_URL" in sh, "the bash path needs the same auto-detect probe"
    py = APPLY.read_text()
    assert "metrics-sink.conf" in py
    assert "CORTEX_VM_HEALTH_URL" in py
    for text in (sh, py):
        assert "HERMES_SERVICES" in text
