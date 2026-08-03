# Hermes Cortex Naming Conventions

## Skill Naming

Skills ported from AgentKore use descriptive names; legacy `hc-` prefixed
names are preserved as **aliases** in frontmatter so old references still resolve.

| Canonical Name | Aliases | Notes |
|----------------|---------|-------|
| `requirements-elicitation` | `hc-elicit`, `elicit` | Requirements elicitation (deep/fast modes, RICE/MoSCoW) |
| `architecture-review` | `hc-party`, `party` | Multi-role architecture review (6-role panel, weighted matrix) |

Other skills keep descriptive names without prefix:
- `agent-flow`, `agent-contract`, `change-test-loop`, `session-manager`
- `state-orchestrator`, `story-slicing`, `product-requirements`

## Versioning Policy

Each skill has a `version:` field in YAML frontmatter:

| Bump | When | Example |
|------|------|---------|
| **Major** | Breaking interface/output format changes | 1.x → 2.x |
| **Minor** | New features, sections, expanded methodology | 1.1 → 1.2 |
| **Patch** | Fixes, clarifications, corrections | 1.0.0 → 1.0.1 |

Current versions tracked in `docs/SKILLS-MANIFEST.md`.

## When to Bump

- Patch: fixing a typo, clarifying a step, adding a pitfall
- Minor: adding a new mode (deep/fast), new workflow section, expanded triggers
- Major: renaming the skill, changing output format, removing features

## Checking Installed Versions

```bash
for skill in requirements-elicitation architecture-review agent-flow; do
  echo "$skill: $(grep "^version:" ~/.hermes/skills/software-development/$skill/SKILL.md 2>/dev/null | sed 's/^version: //')"
done
```
