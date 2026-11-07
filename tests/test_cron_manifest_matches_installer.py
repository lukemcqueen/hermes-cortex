"""Prove the cron-manifest.yaml schedules agree with the installer create_cron
blocks for every cron they both declare.

The manifest (ops/install/cron-manifest.yaml) is the declarative source of
truth; the installers (install-crons.sh / install-orch-crons.sh /
install-dream-crons.sh) independently carry `create_cron "NAME" "BASE-SCHEDULE"`
blocks. A schedule edited in one but not the other silently re-installs the
old cadence on the next fleet-update, so a drift here is a real bug.

Both sides are parsed as TEXT (no yaml dependency), mirroring the
test_retired_orch_crons.py convention. The BASE schedule is compared — the
per-host minute stagger (cksum(hostname:cron-name) % 60) is applied at install
time, not baked into either source, so the two literals must be equal.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "ops" / "install" / "cron-manifest.yaml"
INSTALLERS = [
    REPO / "ops" / "scripts" / "install-crons.sh",
    REPO / "ops" / "scripts" / "install" / "install-orch-crons.sh",
    REPO / "ops" / "scripts" / "install" / "install-dream-crons.sh",
]


def _manifest_schedules() -> dict[str, str]:
    """name -> schedule, parsed from the manifest (text, no yaml)."""
    schedules: dict[str, str] = {}
    name: str | None = None
    for line in MANIFEST.read_text().splitlines():
        m = re.match(r"^- name:\s*(\S+)", line)
        if m:
            name = m.group(1)
            continue
        s = re.match(r"^\s+schedule:\s*'?\"?([^'\"]+)'?\"?\s*$", line)
        if s and name and name not in schedules:
            schedules[name] = s.group(1).strip()
    return schedules


def _installer_schedules() -> dict[str, str]:
    """name -> BASE schedule, parsed from the installers' create_cron blocks.

    The create_cron call always carries the name and schedule as the first two
    quoted args on the SAME line (`create_cron "name" "schedule" \\`), so a
    line-anchored regex is sufficient and immune to the multi-line prompt body.
    """
    schedules: dict[str, str] = {}
    for path in INSTALLERS:
        for line in path.read_text().splitlines():
            m = re.match(r'\s*create_cron\s+"([^"]+)"\s+"([^"]+)"', line)
            if m:
                schedules[m.group(1)] = m.group(2)
    return schedules


def test_shared_crons_have_matching_manifest_and_installer_schedules():
    manifest = _manifest_schedules()
    installer = _installer_schedules()
    shared = set(manifest) & set(installer)
    assert shared, "no shared names — a parser is broken or the two sources are disjoint"
    drift = {n: (manifest[n], installer[n]) for n in shared if manifest[n] != installer[n]}
    assert not drift, f"manifest ↔ installer schedule drift: {drift}"


def test_the_consolidated_workday_crons_are_two_a_day():
    """Guard the cadence-policy consolidation: the fixer and bus inbox jobs are
    a single 08/20 weekday job each — no three-job trio, no midday slot."""
    installer = _installer_schedules()
    assert installer.get("agent-fixer-workday") == "0 8,20 * * 1-5"
    assert installer.get("cortex-bus-workday") == "0 8,20 * * 1-5"
    assert "agent-fixer-evening" not in installer
    assert "agent-fixer-overnight" not in installer
    assert "cortex-bus-evening" not in installer
    assert "cortex-bus-overnight" not in installer


def _create_cron_line_count() -> int:
    """Total `create_cron "…"` invocation lines across the installers."""
    n = 0
    for path in INSTALLERS:
        n += len(re.findall(r'\s*create_cron\s+"', path.read_text()))
    return n


def test_every_create_cron_line_carries_its_schedule():
    """Edge case: the installer parser is line-anchored, so a create_cron whose
    schedule is written on the NEXT line would be silently missed (the name
    simply never enters _installer_schedules). Guard that every invocation line
    actually produced a (name, schedule) pair — a mismatch means a bare
    ``create_cron "x"`` line went unparsed and the coverage is a false green."""
    parsed = len(_installer_schedules())
    total = _create_cron_line_count()
    assert total == parsed, (
        f"{total - parsed} create_cron line(s) carry no inline schedule — "
        "the line-anchored regex missed them and the coverage over-reports"
    )


def test_every_installer_cron_is_declared_in_the_manifest():
    installer = set(_installer_schedules())
    manifest = set(_manifest_schedules())
    missing = sorted(installer - manifest)
    assert not missing, f"installer crons with no manifest entry (orphans): {missing}"


def test_every_manifest_cron_has_an_installer():
    manifest = set(_manifest_schedules())
    installer = set(_installer_schedules())
    missing = sorted(manifest - installer)
    assert not missing, f"manifest crons with no installer create_cron: {missing}"


def test_the_parsers_return_the_full_surface():
    """Non-vacuity: a broken regex (or an emptied manifest) must read as a
    failure, not as a green 'no drift' over an empty set."""
    assert len(_manifest_schedules()) >= 50, "manifest parser returned a suspiciously small set"
    assert _create_cron_line_count() >= 50, "installer parser returned a suspiciously small set"