#!/usr/bin/env python3
"""
fleet-audit — Fleet Ready Score validator for Hermes Cortex agent registries.

Reads agent-registry.json and validates each agent against Fleet Ready Score
levels (F0-F3). Currently supports F1 validation per PRD-005 REQ-003.

Usage:
    fleet-audit --level F1 [--registry path] [--suggest]
    fleet-audit --level F2 [--registry path]   # Future
    fleet-audit --level F3 [--registry path]   # Future

Exit codes:
    0 — All checks pass
    1 — One or more checks fail (or registry not found)
"""

import argparse
import json
import os
import sys
from pathlib import Path

FLEET_CONCERN_FIELDS = {
    "identity": {
        "label": "Identity & Trust",
        "required": ["principal"],
        "subfields": {
            "principal": ["type", "permissions", "tool_scope", "version"]
        }
    },
    "topology": {
        "label": "Topology",
        "required": ["type", "parent"],
        "subfields": {}
    },
    "choreography": {
        "label": "Choreography",
        "required": ["bus_access", "inbox", "handoff_schemas"],
        "subfields": {}
    },
    "economics": {
        "label": "Economics",
        "required": ["budget"],
        "subfields": {
            "budget": ["daily_token_cap", "concurrent_runs", "cost_center"]
        }
    },
    "sovereign_control": {
        "label": "Sovereign Control",
        "required": ["autonomy_tier", "kill_switch", "allow_destructive_ops", "deny_paths"],
        "subfields": {}
    }
}

ADDITIONAL_F1_SECTIONS = {
    "observability": {
        "label": "Observability",
        "required": ["langfuse", "log_level", "tracing", "judge_scorer"],
        "subfields": {}
    },
    "service_layer": {
        "label": "Service Layer",
        "required": ["type", "health_endpoint", "auto_remediate"],
        "subfields": {}
    },
    "capabilities": {
        "label": "Capabilities",
        "required": ["has_git", "has_sudo", "has_cron_tool", "has_terminal", "bus_access", "maintenance_window"],
        "subfields": {
            "git": ["remote", "default_branch", "repo_path"],
            "deploy": ["update_method", "doctor_path"]
        }
    }
}


def find_registry(path_hint=None):
    """Find the agent registry JSON file, searching common locations."""
    if path_hint:
        p = Path(path_hint)
        if p.exists():
            return p

    candidates = [
        Path.home() / ".hermes-cortex" / "state" / "agent-registry.json",
        Path.home() / "hermes-cortex" / "ops" / "install" / "deploy" / "agent-registry.json.example",
        Path.home() / "hermes-cortex" / "ops" / "install" / "deploy" / "agent-registry.template.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def check_required_fields(agent_key, agent, section_name, spec):
    """Check that a section has all required fields populated.

    Returns list of (field_path, issue) tuples.
    """
    issues = []
    section = agent.get(section_name, {})

    for field in spec["required"]:
        if field not in section:
            issues.append((f"{agent_key}.{section_name}.{field}", "MISSING"))
        elif section[field] is None and field == "parent":
            # Root orchestrators legitimately have null parent
            pass
        elif section[field] is None:
            issues.append((f"{agent_key}.{section_name}.{field}", "NULL"))
        elif isinstance(section[field], (list, dict)) and len(section[field]) == 0:
            # Empty lists/objects are allowed but noted
            pass
        elif isinstance(section[field], str) and section[field].startswith("{{"):
            issues.append((f"{agent_key}.{section_name}.{field}", "TEMPLATE_UNREPLACED"))

    # Check subfields
    for parent_field, subfields in spec.get("subfields", {}).items():
        parent = section.get(parent_field, {})
        if not isinstance(parent, dict):
            issues.append((f"{agent_key}.{section_name}.{parent_field}", "NOT_A_DICT"))
            continue
        for subfield in subfields:
            full_path = f"{agent_key}.{section_name}.{parent_field}.{subfield}"
            if subfield not in parent:
                issues.append((full_path, "MISSING"))
            elif parent[subfield] is None:
                issues.append((full_path, "NULL"))
            elif isinstance(parent[subfield], str) and parent[subfield].startswith("{{"):
                issues.append((full_path, "TEMPLATE_UNREPLACED"))

    return issues


def validate_f1(registry, suggest=False):
    """Validate all agents against F1 (Registry + Permissions)."""
    results = {}
    total_issues = 0
    agent_names = registry.get("agents", {})

    if not agent_names:
        print("ERROR: No agents found in registry.")
        sys.exit(1)

    for agent_key, agent in agent_names.items():
        agent_issues = []
        agent_warnings = []

        # Check required identity fields
        name = agent.get("name", agent_key)
        role = agent.get("role", "unknown")
        platform = agent.get("platform", "unknown")
        health_method = agent.get("health_method", "unknown")

        # Check core identity fields
        core_fields = ["name", "role", "hostname", "platform", "health_method", "inbox_user"]
        for field in core_fields:
            if field not in agent or agent[field] is None:
                agent_issues.append((f"{agent_key}.{field}", "MISSING"))

        # Check fleet concerns (the 5 concerns)
        fleet_concerns = agent.get("fleet_concerns", {})
        if not fleet_concerns:
            agent_issues.append((f"{agent_key}.fleet_concerns", "MISSING_SECTION"))
        else:
            for concern_key, concern_spec in FLEET_CONCERN_FIELDS.items():
                issues = check_required_fields(agent_key, fleet_concerns, concern_key, concern_spec)
                agent_issues.extend(issues)

        # Check observability
        obs_issues = check_required_fields(agent_key, agent, "observability", ADDITIONAL_F1_SECTIONS["observability"])
        agent_issues.extend(obs_issues)

        # Check service_layer
        sl_issues = check_required_fields(agent_key, agent, "service_layer", ADDITIONAL_F1_SECTIONS["service_layer"])
        agent_issues.extend(sl_issues)

        # Check capabilities
        cap_issues = check_required_fields(agent_key, agent, "capabilities", ADDITIONAL_F1_SECTIONS["capabilities"])
        agent_issues.extend(cap_issues)

        # Check bus_access consistency between capabilities and fleet_concerns.choreography
        cap_bus = agent.get("capabilities", {}).get("bus_access")
        chore_bus = fleet_concerns.get("choreography", {}).get("bus_access")
        if cap_bus and chore_bus and cap_bus != chore_bus:
            agent_issues.append((
                f"{agent_key}.bus_access MISMATCH",
                f"capabilities has '{cap_bus}' but fleet_concerns.choreography has '{chore_bus}'"
            ))

        # Check sovereignty — F1 requires autonomy_tier >= F1
        sov = fleet_concerns.get("sovereign_control", {})
        tier = sov.get("autonomy_tier", "")
        if tier and tier not in ("F1", "F2", "F3"):
            agent_warnings.append(f"{agent_key}.fleet_concerns.sovereign_control.autonomy_tier: '{tier}' — expected F1/F2/F3")

        # Check health_method consistency
        if role == "orchestrator" and health_method != "http":
            agent_warnings.append(f"{agent_key}.health_method: '{health_method}' — orchestrators should use 'http'")
        if not agent.get("is_server", False) and health_method == "http":
            agent_warnings.append(f"{agent_key}.health_method: '{health_method}' but is_server=false — non-servers should use 'inbox'")

        results[agent_key] = {
            "name": name,
            "role": role,
            "issues": agent_issues,
            "warnings": agent_warnings,
            "pass": len(agent_issues) == 0
        }
        total_issues += len(agent_issues)

    return results, total_issues


def format_results(results, suggest=False):
    """Format audit results for display."""
    lines = []
    all_pass = all(r["pass"] for r in results.values())

    lines.append(f"{'Agent':<18} {'Role':<16} {'Status':<10}")
    lines.append("-" * 46)

    for agent_key, r in sorted(results.items()):
        status = "✅ PASS" if r["pass"] else "❌ FAIL"
        lines.append(f"{agent_key:<18} {r['role']:<16} {status:<10}")

    lines.append("")
    if all_pass:
        lines.append("🎉 All agents pass F1 validation.")
    else:
        lines.append(f"⚠️  {sum(1 for r in results.values() if not r['pass'])} agent(s) have issues.")

    lines.append("")
    for agent_key, r in sorted(results.items()):
        if not r["issues"] and not r["warnings"]:
            continue
        lines.append(f"── {r['name']} ({agent_key}) ──")
        if r["issues"]:
            lines.append("  Issues:")
            for path, issue in r["issues"]:
                lines.append(f"    ❌ {path}: {issue}")
        if r["warnings"]:
            lines.append("  Warnings:")
            for w in r["warnings"]:
                lines.append(f"    ⚠️  {w}")
        lines.append("")

    if suggest and not all_pass:
        lines.append("── Suggested Fixes ──")
        lines.append("")
        for agent_key, r in sorted(results.items()):
            if not r["issues"]:
                continue
            lines.append(f"### {r['name']} ({agent_key})")
            for path, issue in r["issues"]:
                parts = path.split(".")
                if len(parts) >= 4:
                    # fleet_concerns path
                    concern = parts[2]
                    field = ".".join(parts[3:])
                    lines.append(f"- **{path}**: Add `{field}` under `fleet_concerns.{concern}`")
                elif issue == "MISSING_SECTION":
                    lines.append(f"- **{path}**: Add `fleet_concerns` section with all 5 concerns")
                elif issue == "MISSING":
                    field = parts[-1]
                    lines.append(f"- **{path}**: Add required field `{field}`")
                elif issue == "NULL":
                    lines.append(f"- **{path}**: Set to a non-null value")
                elif issue == "TEMPLATE_UNREPLACED":
                    lines.append(f"- **{path}**: Replace `{{{{...}}}}` placeholder with real value")
                else:
                    lines.append(f"- **{path}**: {issue}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Fleet Ready Score validator for Hermes Cortex agent registries."
    )
    parser.add_argument(
        "--level", "-l",
        choices=["F0", "F1", "F2", "F3"],
        default="F1",
        help="Fleet Ready Score level to validate against (default: F1)"
    )
    parser.add_argument(
        "--registry", "-r",
        help="Path to agent-registry.json (searches standard locations if omitted)"
    )
    parser.add_argument(
        "--suggest", "-s",
        action="store_true",
        help="Print suggested fixes for failing checks"
    )

    args = parser.parse_args()

    registry_path = find_registry(args.registry)
    if not registry_path:
        print("ERROR: Could not find agent-registry.json.")
        print("Provide a path with --registry or deploy to ~/.hermes-cortex/state/agent-registry.json")
        sys.exit(1)

    try:
        with open(registry_path) as f:
            registry = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {registry_path}: {e}")
        sys.exit(1)
    except IOError as e:
        print(f"ERROR: Cannot read {registry_path}: {e}")
        sys.exit(1)

    version = registry.get("version", "unknown")
    print(f"📋 Agent Registry v{version} — {registry_path}")
    print(f"   Agents: {len(registry.get('agents', {}))}")
    print(f"   Level:  {args.level}")
    if args.suggest:
        print(f"   Mode:   Suggest fixes")
    print()

    if args.level == "F0":
        # F0: Agents exist (trivially pass if registry has agents)
        count = len(registry.get("agents", {}))
        if count > 0:
            print(f"✅ F0: {count} agents registered — baseline met.")
        else:
            print("❌ F0: No agents registered.")
            sys.exit(1)
        return

    if args.level in ("F3",):
        print(f"⚠️  F3 validation not yet implemented.")
        print("   F3 adds: unattended operation, kill switch, audit trail.")
        sys.exit(0)

    # Run F1 validation (F2 includes all F1 checks)
    results, total_issues = validate_f1(registry, suggest=args.suggest)

    if args.level == "F2":
        # Additional F2 checks: budget fields, cost_center, observability
        for agent_key, agent in registry.get("agents", {}).items():
            r = results.get(agent_key, {})
            if not r:
                continue
            fleet = agent.get("fleet_concerns", {})
            eco = fleet.get("economics", {})
            budget = eco.get("budget", {})

            # Check budget fields exist
            if not budget:
                r["issues"].append((f"{agent_key}.fleet_concerns.economics.budget", "MISSING (F2)"))
            else:
                if not budget.get("daily_token_cap") or budget["daily_token_cap"] == "{{TOKEN_CAP}}":
                    r["issues"].append((f"{agent_key}.fleet_concerns.economics.budget.daily_token_cap",
                                        "MISSING_OR_PLACEHOLDER (F2)"))
                if not budget.get("cost_center") or budget["cost_center"] == "{{COST_CENTER}}":
                    r["issues"].append((f"{agent_key}.fleet_concerns.economics.budget.cost_center",
                                        "MISSING_OR_PLACEHOLDER (F2)"))

            # Check observability langfuse
            obs = agent.get("observability", {})
            if not obs.get("langfuse"):
                r["issues"].append((f"{agent_key}.observability.langfuse", "FALSE (F2: required for cost visibility)"))

            # Recalculate pass/fail
            r["pass"] = len(r["issues"]) == 0
            total_issues = sum(len(v["issues"]) for v in results.values())

    output = format_results(results, suggest=args.suggest)
    print(output)

    all_pass = all(r["pass"] for r in results.values())
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
