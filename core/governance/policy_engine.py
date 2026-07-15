"""
Policy Engine — Attribute-based access control for agent tool governance.

Extends the governance enforcer plugin beyond binary lock checking.
Evaluates ``PolicyRule`` against ``PolicyContext`` to produce ``PolicyEffect``.

Usage::

    engine = PolicyEngine()
    engine.add_rule(PolicyRule(
        effect=PolicyEffect.ALLOW,
        subject="*",
        action="*",
        resource="*",
        condition=lambda ctx: ctx.has_governance_lock,
    ))
    result = engine.evaluate(PolicyContext(tool="write_file", agent="titus"))
    # → PolicyResult(effect=PolicyEffect.ALLOW, rule="default:lock-required")

See: docs/research/enterprise-grade-hermes-cortex.md § "Generalize governance"
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


# ── Policy effect ───────────────────────────────────────────────────────────


class PolicyEffect(str, Enum):
    """What the policy rule says about the requested action."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


# ── Policy context (evaluation input) ───────────────────────────────────────


@dataclass
class PolicyContext:
    """Everything the policy engine knows about the current request.

    Fields are intentionally optional — a rule that doesn't need agent identity
    won't fail because the field is unset.
    """

    # Who is acting
    agent: str = ""                # Agent name: "titus", "moses", "guest"
    agent_role: str = ""           # Role: "devops", "orchestrator", "operator"

    # What they're doing
    tool: str = ""                 # Tool name: "write_file", "terminal", "patch"
    action: str = ""               # Action: "write", "create", "delete", "list"
    command: str = ""              # Full command string (for terminal)

    # Where they're doing it
    resource: str = ""             # Resource path / name: "/tmp/test.txt", "my-skill"
    environment: str = ""          # "development", "staging", "production"
    tenant: str = ""               # Multi-tenant namespace

    # Context
    has_governance_lock: bool = False
    time: str = ""                 # ISO-8601 timestamp, auto-filled if empty

    # Resource metadata
    resource_classification: str = ""   # "public", "confidential", "pii"
    resource_owner: str = ""            # Owner of the resource being modified

    # Task-derived fields (§4.1 of harness-v3-requirements)
    task_id: str = ""
    task_status: str = ""
    task_criterion_id: str = ""
    task_step_id: str = ""
    task_allowed_scope: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.time:
            self.time = datetime.utcnow().isoformat()


# ── Policy rule ─────────────────────────────────────────────────────────────


ConditionFn = Callable[[PolicyContext], bool]


@dataclass
class PolicyRule:
    """A single policy rule.

    ``subject``, ``action``, and ``resource`` support glob patterns
    (``*``, ``?``, ``[abc]``) via :func:`fnmatch.filter`.

    ``condition`` is an optional predicate for context-dependent logic
    (time-of-day, governance lock state, approval chain, etc.).
    """

    effect: PolicyEffect = PolicyEffect.DENY
    subject: str = "*"              # Glob: "titus", "moses", "guest", "*"
    action: str = "*"              # Glob: "write", "create", "read", "*"
    resource: str = "*"            # Glob: "/tmp/*", "*/secrets/*", "*"
    condition: Optional[ConditionFn] = None
    description: str = ""          # Human-readable: "Default deny all"
    priority: int = 0              # Higher = evaluated first; 0 = normal

    def matches(self, ctx: PolicyContext) -> bool:
        """Check if this rule applies to the given context."""
        if not fnmatch.fnmatch(ctx.agent, self.subject):
            return False
        if not fnmatch.fnmatch(ctx.action, self.action):
            return False
        if not fnmatch.fnmatch(ctx.resource, self.resource):
            return False
        if self.condition and not self.condition(ctx):
            return False
        return True


# ── Policy result ───────────────────────────────────────────────────────────


@dataclass
class PolicyResult:
    """The outcome of evaluating all rules against a context."""

    effect: PolicyEffect = PolicyEffect.DENY
    rule: str = "default:deny-all"  # Rule description that matched
    matched_rules: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Built-in condition helpers ──────────────────────────────────────────────


def has_lock(ctx: PolicyContext) -> bool:
    """True when a governance lock is active."""
    return ctx.has_governance_lock


def not_has_lock(ctx: PolicyContext) -> bool:
    """True when NO governance lock is active."""
    return not ctx.has_governance_lock


def is_production(ctx: PolicyContext) -> bool:
    """True when the target environment is production."""
    return ctx.environment == "production"


def is_confidential(ctx: PolicyContext) -> bool:
    """True when the resource is classified as confidential or PII."""
    return ctx.resource_classification in ("confidential", "pii", "restricted")


def during_business_hours(ctx: PolicyContext) -> bool:
    """True between 08:00 and 18:00 UTC."""
    import re
    m = re.search(r"T(\d{2}):", ctx.time)
    if not m:
        return True
    hour = int(m.group(1))
    return 8 <= hour < 18


def in_task_scope(ctx: PolicyContext) -> bool:
    """True when ctx.resource matches one of the active task's allowed_scope globs."""
    if not ctx.task_allowed_scope:
        return True  # no task = no scope restriction beyond the existing lock check
    return any(fnmatch.fnmatch(ctx.resource, pat) for pat in ctx.task_allowed_scope)


def has_valid_provenance(ctx: PolicyContext) -> bool:
    """True when a criterion_id/step_id were supplied and are non-empty.

    Full validation (criterion exists on the active task) happens in the
    envelope check in the MCP tool layer, where the ledger is directly
    available — this predicate only screens for the field being present,
    since PolicyContext deliberately stays engine-agnostic about ledger
    internals.
    """
    return bool(ctx.task_criterion_id and ctx.task_step_id)


# ── Policy engine ───────────────────────────────────────────────────────────


FIRST_MATCH = "first_match"
DENY_OVERRIDES = "deny_overrides"


class PolicyEngine:
    """Evaluates tool actions against a set of policy rules.

    Two evaluation modes::

        FIRST_MATCH (default)
            Returns the first rule with a matching subject/action/resource.

        DENY_OVERRIDES
            Evaluates all rules. If any rule says DENY, the result is DENY.
            Otherwise, the first ALLOW or REQUIRE_APPROVAL wins.
    """

    def __init__(self, mode: str = FIRST_MATCH):
        self.rules: list[PolicyRule] = []
        self.mode = mode
        self._build_defaults()

    def _build_defaults(self) -> None:
        """Seed with sensible defaults replicating current enforcer behavior.

        These can be overridden by adding higher-priority rules.
        """
        self.rules = [
            # Write outside active task's allowed_scope — highest priority
            PolicyRule(
                effect=PolicyEffect.DENY, subject="*", action="write", resource="*",
                condition=lambda ctx: ctx.has_governance_lock and bool(ctx.task_id) and not in_task_scope(ctx),
                description="Write outside active task's allowed_scope",
                priority=20,
            ),
            # Lock present → allow everything (current behavior)
            PolicyRule(
                effect=PolicyEffect.ALLOW,
                subject="*", action="write", resource="*",
                condition=has_lock,
                description="Active governance lock allows writes",
                priority=10,
            ),
            # Lock present → allow manage actions
            PolicyRule(
                effect=PolicyEffect.ALLOW,
                subject="*", action="manage", resource="*",
                condition=has_lock,
                description="Active governance lock allows management",
                priority=10,
            ),
            # No lock → deny all writes
            PolicyRule(
                effect=PolicyEffect.DENY,
                subject="*", action="write", resource="*",
                condition=not_has_lock,
                description="No governance lock → writes denied",
                priority=5,
            ),
            # No lock → deny all management
            PolicyRule(
                effect=PolicyEffect.DENY,
                subject="*", action="manage", resource="*",
                condition=not_has_lock,
                description="No governance lock → management denied",
                priority=5,
            ),
            # Everything else → allow (read tools, etc.)
            PolicyRule(
                effect=PolicyEffect.ALLOW,
                subject="*", action="*", resource="*",
                description="Default allow for non-write actions",
                priority=0,
            ),
        ]

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a rule.  Higher-priority rules are evaluated first."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rules(self, description_pattern: str) -> int:
        """Remove rules whose description matches a glob pattern. Returns count removed."""
        before = len(self.rules)
        self.rules = [r for r in self.rules if not fnmatch.fnmatch(r.description, description_pattern)]
        return before - len(self.rules)

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """Evaluate all rules and return a decision."""
        result = PolicyResult()
        matched: list[tuple[PolicyRule, int]] = []

        for i, rule in enumerate(self.rules):
            if rule.matches(ctx):
                matched.append((rule, i))
                result.matched_rules.append(f"#{i}:{rule.description}")

        if not matched:
            return result  # default DENY

        if self.mode == FIRST_MATCH:
            rule, _ = matched[0]
            result.effect = rule.effect
            result.rule = rule.description
        elif self.mode == DENY_OVERRIDES:
            for rule, _ in matched:
                if rule.effect == PolicyEffect.DENY:
                    result.effect = PolicyEffect.DENY
                    result.rule = f"deny-override:{rule.description}"
                    return result
            # No DENY → first non-deny wins
            first = matched[0][0]
            result.effect = first.effect
            result.rule = first.description

        return result


# ── Convenience: classify tool + args → action ──────────────────────────────


def classify_action(tool: str, command: str = "", cron_action: str = "", skill_action: str = "") -> str:
    """Classify a tool call into a policy action category.

    Returns one of: "write", "read", "manage", "deploy", "delete", "admin"
    """
    write_tools = {"write_file", "patch"}
    read_tools = {"read_file", "web_search", "browser_navigate"}
    manage_tools = {"cronjob", "skill_manage"}

    if tool in write_tools:
        return "write"
    if tool in read_tools:
        return "read"
    if tool == "terminal":
        write_patterns = [
            r"rm\s", r"mv\s", r"cp\s", r"install\s", r"apt", r"dpkg",
            r"git\s+(push|commit|merge|rebase|reset)",
            r"docker\s+(run|build|push|commit|rmi|system\s+prune)",
            r"echo\s+.*[>|>>]\s",
        ]
        for pat in write_patterns:
            if re.search(pat, command):
                return "write"
        return "read"
    if tool in manage_tools:
        write_actions = {"create", "update", "remove", "edit", "delete", "patch", "write_file"}
        if cron_action in write_actions or skill_action in write_actions:
            return "manage"
        return "read"
    return "read"


def build_context(
    tool: str,
    agent: str = "",
    command: str = "",
    cron_action: str = "",
    skill_action: str = "",
    resource: str = "",
    environment: str = "",
    has_lock: bool = False,
    **kwargs,
) -> PolicyContext:
    """Build a PolicyContext from tool-call arguments."""
    action = classify_action(tool, command, cron_action, skill_action)
    if not resource:
        if command:
            resource = command[:80]
        elif cron_action:
            resource = f"cron:{cron_action}"
        elif skill_action:
            resource = f"skill:{skill_action}"
    return PolicyContext(
        agent=agent,
        tool=tool,
        action=action,
        command=command,
        resource=resource or tool,
        environment=environment,
        has_governance_lock=has_lock,
    )
