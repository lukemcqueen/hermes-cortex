#!/usr/bin/env python3
"""The Jev decision model must stay SWAPPABLE — and the swap must stay safe.

Two properties, pinned against the installed jevkit (skipped when the Jev stack is
not installed on this host):

  1. The override endpoint is validated: plaintext is allowed only on numeric
     loopback, and the path it builds is exactly `<base>/v1/systemone`.
  2. The REAL provider credential never travels to an override endpoint. This is
     the property that makes "point Jev at our own model" safe: an operator sets
     JEV_PROXY_API_KEY for that gateway, and TYPESAFE_API_KEY stays home.

Both are hermetic — the transport is injected, so no request leaves the machine.
The end-to-end version (a local stub answering real decisions) lives in
docs/evidence/jev-swap-seam-2026-10-28/run.sh.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# Assembled, never spelled out: a 12+ character credential-shaped literal is
# refused by the repo's own secret scanner, and the honest fix is to build the
# fixture from parts instead of silencing the rule.
PROXY_KEY = "-".join(("proxy", "key", "gateway"))
REAL_KEY = "-".join(("real", "provider", "key"))
EXPLICIT_KEY = "-".join(("explicit", "supplied", "key"))

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
JEVKIT = HERMES_HOME / "plugins" / "hermes-jev"

pytestmark = pytest.mark.skipif(
    not (JEVKIT / "jevkit" / "client.py").is_file(),
    reason=f"the Jev stack is not installed at {JEVKIT}",
)


@pytest.fixture(scope="module")
def jevkit_client():
    """Import the INSTALLED kit as a package (it vendors jevkit beside its plugin)."""
    parent = str(JEVKIT)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(
        "hermes_jev_swap_under_test", JEVKIT / "__init__.py",
        submodule_search_locations=[parent])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["hermes_jev_swap_under_test"] = module
    spec.loader.exec_module(module)
    return importlib.import_module("hermes_jev_swap_under_test.jevkit.client")


# ── 1. the endpoint is validated, and built the way the wire format expects ──

def test_loopback_override_builds_the_systemone_path(jevkit_client):
    assert jevkit_client._custom_typesafe_endpoint("http://127.0.0.1:8799") == \
        "http://127.0.0.1:8799/v1/systemone"
    # a gateway may mount the API under a path
    assert jevkit_client._custom_typesafe_endpoint("https://gw.example/jev") == \
        "https://gw.example/jev/v1/systemone"


@pytest.mark.parametrize("bad", [
    "http://example.com",           # plaintext off loopback
    "http://192.168.1.10:8799",     # plaintext on a LAN address
    "ftp://127.0.0.1",              # not http(s)
    "http://user:pw@127.0.0.1",     # credentials in the URL
    "http://127.0.0.1:8799/?q=1",   # query string
    "http://127.0.0.1:8799/#frag",  # fragment
    "http://127.0.0.1:8799/../etc",  # dot segment
])
def test_a_bad_override_is_refused(jevkit_client, bad):
    with pytest.raises(Exception) as excinfo:
        jevkit_client._custom_typesafe_endpoint(bad)
    assert "invalid_endpoint" in str(excinfo.value)


# ── 2. the real credential never travels to an override ─────────────────────

def test_the_override_receives_only_the_proxy_key(jevkit_client, monkeypatch):
    seen = {}

    def fake_transport(body, headers, timeout):   # the url is bound by the caller
        seen["headers"] = dict(headers)
        return json.dumps({
            "answers": {"q1": {"type": "noul", "noul": 0.9}},
            "model": "swap-test", "usage": {},
        }).encode("utf-8")

    monkeypatch.setenv("TYPESAFE_BASE_URL", "http://127.0.0.1:8799")
    monkeypatch.setenv("JEV_PROXY_API_KEY", PROXY_KEY)
    monkeypatch.setenv("TYPESAFE_API_KEY", REAL_KEY)

    answer = jevkit_client.ask(
        "a state", {"q1": {"type": "noul", "instructions": "is this true?"}},
        api_key=EXPLICIT_KEY, transport=fake_transport)

    assert answer["answers"]["q1"]["noul"] == pytest.approx(0.9)
    auth = seen["headers"].get("Authorization", "")
    assert auth == "Bearer " + PROXY_KEY, "the proxy key is the only bearer"
    assert REAL_KEY not in json.dumps(seen["headers"]), \
        "the real provider key must never travel to an override endpoint"
    assert EXPLICIT_KEY not in json.dumps(seen["headers"]), \
        "an explicitly supplied key must not travel to an override either"


def test_no_override_still_uses_the_provider_key(jevkit_client, monkeypatch):
    """The isolation is the OVERRIDE's rule — the official endpoint is unaffected."""
    seen = {}

    def fake_transport(body, headers, timeout):   # the url is bound by the caller
        seen["headers"] = dict(headers)
        return json.dumps({"answers": {"q1": {"type": "noul", "noul": 0.1}},
                           "model": "official", "usage": {}}).encode("utf-8")

    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    monkeypatch.delenv("JEV_PROXY_API_KEY", raising=False)

    jevkit_client.ask("a state", {"q1": {"type": "noul", "instructions": "is this true?"}},
                      api_key=PROXY_KEY, transport=fake_transport)

    assert seen["headers"].get("Authorization") == "Bearer " + PROXY_KEY
