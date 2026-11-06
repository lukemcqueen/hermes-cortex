#!/usr/bin/env python3
"""Hermetic tests for ops/scripts/fleet-bus-bridge-generate.py internals.

The close review (ADV-14307) required committed coverage for the
cron-expression translator (cron_to_oncalendar / instance_interval) and the
KillMode reprocessor (with_killmode). Expected values below are the MEASURED
outputs of the functions (pinned contracts, not guesses). Import-safe: the
module only runs its CLI under `if __name__ == "__main__"`.
"""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "ops" / "scripts" / "fleet-bus-bridge-generate.py"

_spec = importlib.util.spec_from_file_location("fleet_bus_bridge_generate_ut", GEN)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


@pytest.mark.parametrize("expr,expected", [
    ("0 3 * * *", "*-*-* 03:00:00"),
    ("*/10 * * * *", "*-*-* *:0/10:00"),
    ("0 */2 * * *", "*-*-* *:00/2:00"),
    ("30 9-17 * * 1-5", "Mon..Fri *-*-* 09..17:30:00"),
    ("0 4 * * 1", "Mon *-*-* 04:00:00"),
    ("0 23 * * 6", "Sat *-*-* 23:00:00"),
    ("5 2 * * 0", "Sun *-*-* 02:05:00"),
])
def test_cron_to_oncalendar_supported_shapes(expr, expected):
    assert gen.cron_to_oncalendar(expr) == expected


@pytest.mark.parametrize("expr", ["@daily", "* * * *", "bad", "*/5 * * * * *", ""])
def test_cron_to_oncalendar_unsupported_returns_none(expr):
    assert gen.cron_to_oncalendar(expr) is None


@pytest.mark.parametrize("sched,expected", [
    ({"kind": "every", "every": "2h"}, "*-*-* *:00/2:00"),
    ({"every": "360m"}, "*-*-* *:00/6:00"),
    ({"every": "10m"}, "*-*-* *:0/10:00"),
    ({"display": "every 5m"}, "*-*-* *:0/5:00"),
    ({"every": "70m"}, None),            # does not divide 60 -> refused
    ({"every": "90m"}, None),           # >=60 but not a whole hour -> refused
])
def test_instance_interval_real_shapes(sched, expected):
    assert gen.instance_interval(sched) == expected


def test_with_killmode_adds_after_type_anchor():
    unit = "[Unit]\nDescription=X\n\n[Service]\nType=oneshot\nExecStart=/bin/true\n"
    out = gen.with_killmode(unit)
    assert out is not None and "KillMode=process" in out
    assert out.index("KillMode=process") > out.index("[Service]")


def test_with_killmode_anchorless_unit_is_a_visible_refusal():
    """A unit missing BOTH Type= and ExecStart= must NOT be returned
    byte-identical (that would read as 'already correct') — it is None."""
    unit = "[Unit]\nDescription=X\n"
    assert gen.with_killmode(unit) is None


def test_with_killmode_idempotent():
    unit = "[Unit]\nDescription=X\n\n[Service]\nType=oneshot\nKillMode=process\nExecStart=/bin/true\n"
    assert gen.with_killmode(unit) == unit
