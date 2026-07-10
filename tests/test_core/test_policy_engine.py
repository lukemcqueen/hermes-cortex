"""Tests for core/governance/policy_engine.py"""

from core.governance.policy_engine import (
    DENY_OVERRIDES,
    FIRST_MATCH,
    PolicyContext,
    PolicyEffect,
    PolicyEngine,
    PolicyResult,
    PolicyRule,
    build_context,
    classify_action,
    during_business_hours,
    has_lock,
    is_confidential,
    is_production,
    not_has_lock,
)


# ═════════════════════════════════════════════════════════════════════════════
# PolicyRule
# ═════════════════════════════════════════════════════════════════════════════


class TestPolicyRule:
    def test_subject_glob_match(self):
        rule = PolicyRule(effect=PolicyEffect.ALLOW, subject="titus", action="write")
        assert rule.matches(PolicyContext(agent="titus", action="write")) is True

    def test_subject_glob_wildcard(self):
        rule = PolicyRule(effect=PolicyEffect.ALLOW, subject="*", action="write")
        assert rule.matches(PolicyContext(agent="anyone", action="write")) is True

    def test_subject_no_match(self):
        rule = PolicyRule(effect=PolicyEffect.DENY, subject="moses", action="write")
        assert rule.matches(PolicyContext(agent="titus", action="write")) is False

    def test_action_glob_match(self):
        rule = PolicyRule(effect=PolicyEffect.DENY, action="delete")
        assert rule.matches(PolicyContext(agent="any", action="delete")) is True
        assert rule.matches(PolicyContext(agent="any", action="write")) is False

    def test_resource_glob_match(self):
        rule = PolicyRule(effect=PolicyEffect.DENY, resource="*/secrets/*")
        ctx = PolicyContext(agent="any", action="read", resource="/etc/secrets/password.txt")
        assert rule.matches(ctx) is True

    def test_resource_glob_no_match(self):
        rule = PolicyRule(effect=PolicyEffect.DENY, resource="*/secrets/*")
        ctx = PolicyContext(agent="any", action="read", resource="/tmp/test.txt")
        assert rule.matches(ctx) is False

    def test_condition_returns_false(self):
        rule = PolicyRule(
            effect=PolicyEffect.ALLOW,
            condition=lambda ctx: False,
        )
        assert rule.matches(PolicyContext()) is False

    def test_condition_returns_true(self):
        rule = PolicyRule(
            effect=PolicyEffect.ALLOW,
            condition=lambda ctx: ctx.has_governance_lock,
        )
        assert rule.matches(PolicyContext(has_governance_lock=True)) is True
        assert rule.matches(PolicyContext(has_governance_lock=False)) is False


# ═════════════════════════════════════════════════════════════════════════════
# PolicyEngine — defaults replicating current enforcer behavior
# ═════════════════════════════════════════════════════════════════════════════


class TestPolicyEngineDefaults:
    """Default rules should replicate existing enforcer behavior."""

    def test_write_with_lock_allowed(self):
        engine = PolicyEngine()
        ctx = PolicyContext(agent="titus", action="write", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.ALLOW

    def test_write_without_lock_denied(self):
        engine = PolicyEngine()
        ctx = PolicyContext(agent="titus", action="write", has_governance_lock=False)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.DENY

    def test_manage_with_lock_allowed(self):
        engine = PolicyEngine()
        ctx = PolicyContext(agent="moses", action="manage", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.ALLOW

    def test_manage_without_lock_denied(self):
        engine = PolicyEngine()
        ctx = PolicyContext(agent="moses", action="manage", has_governance_lock=False)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.DENY

    def test_read_without_lock_allowed(self):
        engine = PolicyEngine()
        ctx = PolicyContext(agent="guest", action="read", has_governance_lock=False)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.ALLOW

    def test_result_includes_rule_description(self):
        engine = PolicyEngine()
        ctx = PolicyContext(agent="any", action="write", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert "Active governance lock allows writes" in result.rule

    def test_result_includes_matched_rules(self):
        engine = PolicyEngine()
        ctx = PolicyContext(agent="any", action="write", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert len(result.matched_rules) >= 1

    def test_empty_rules_returns_default_deny(self):
        engine = PolicyEngine()
        engine.rules = []  # Clear all rules
        result = engine.evaluate(PolicyContext(agent="any"))
        assert result.effect == PolicyEffect.DENY
        assert "default:deny-all" in result.rule


# ═════════════════════════════════════════════════════════════════════════════
# PolicyEngine — custom rules and overrides
# ═════════════════════════════════════════════════════════════════════════════


class TestPolicyEngineCustom:
    def test_custom_rule_overrides_default(self):
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.DENY,
            subject="guest",
            action="write",
            description="Guests cannot write",
            priority=20,  # Higher than default (10)
        ))
        # Guest with lock — default would ALLOW, custom rule should DENY
        ctx = PolicyContext(agent="guest", action="write", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.DENY

    def test_custom_rule_lower_priority(self):
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.ALLOW,
            subject="titus",
            action="*",
            description="Titus can do anything",
            priority=1,  # Lower than default (10)
        ))
        ctx = PolicyContext(agent="titus", action="write", has_governance_lock=False)
        result = engine.evaluate(ctx)
        # Default "no lock → deny" has priority 5, higher than 1
        assert result.effect == PolicyEffect.DENY

    def test_deny_overrides_mode(self):
        engine = PolicyEngine(mode=DENY_OVERRIDES)
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.DENY,
            subject="*",
            action="write",
            resource="*/etc/shadow",
            description="Never write to shadow",
            priority=20,
        ))
        ctx = PolicyContext(agent="root", action="write", resource="/etc/shadow", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.DENY

    def test_require_approval(self):
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.REQUIRE_APPROVAL,
            subject="*",
            action="deploy",
            condition=is_production,
            description="Approval needed for prod deploy",
            priority=20,
        ))
        ctx = PolicyContext(agent="dev", action="deploy", environment="production", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.REQUIRE_APPROVAL

    def test_remove_rules(self):
        engine = PolicyEngine()
        count = engine.remove_rules("Default*")
        assert count > 0

    def test_remove_rules_count_zero(self):
        engine = PolicyEngine()
        count = engine.remove_rules("NonexistentRuleXYZ")
        assert count == 0


# ═════════════════════════════════════════════════════════════════════════════
# classify_action
# ═════════════════════════════════════════════════════════════════════════════


class TestClassifyAction:
    def test_write_file_is_write(self):
        assert classify_action("write_file") == "write"

    def test_patch_is_write(self):
        assert classify_action("patch") == "write"

    def test_read_file_is_read(self):
        assert classify_action("read_file") == "read"

    def test_web_search_is_read(self):
        assert classify_action("web_search") == "read"

    def test_terminal_rm_is_write(self):
        assert classify_action("terminal", command="rm -rf /tmp") == "write"

    def test_terminal_ls_is_read(self):
        assert classify_action("terminal", command="ls -la") == "read"

    def test_terminal_git_push_is_write(self):
        assert classify_action("terminal", command="git push origin main") == "write"

    def test_terminal_echo_redirect_is_write(self):
        assert classify_action("terminal", command="echo 'data' > file.txt") == "write"

    def test_cronjob_create_is_manage(self):
        assert classify_action("cronjob", cron_action="create") == "manage"

    def test_cronjob_list_is_read(self):
        assert classify_action("cronjob", cron_action="list") == "read"

    def test_skill_manage_delete_is_manage(self):
        assert classify_action("skill_manage", skill_action="delete") == "manage"

    def test_skill_manage_view_is_read(self):
        assert classify_action("skill_manage", skill_action="view") == "read"

    def test_unknown_tool_is_read(self):
        assert classify_action("browser_navigate") == "read"

    def test_empty_tool_is_read(self):
        assert classify_action("") == "read"


# ═════════════════════════════════════════════════════════════════════════════
# build_context
# ═════════════════════════════════════════════════════════════════════════════


class TestBuildContext:
    def test_builds_write_context(self):
        ctx = build_context(tool="write_file", agent="titus", has_lock=True)
        assert ctx.agent == "titus"
        assert ctx.tool == "write_file"
        assert ctx.action == "write"
        assert ctx.has_governance_lock is True

    def test_builds_read_context(self):
        ctx = build_context(tool="read_file", has_lock=False)
        assert ctx.action == "read"

    def test_builds_terminal_write_context(self):
        ctx = build_context(tool="terminal", command="rm -rf /tmp/test")
        assert ctx.action == "write"

    def test_builds_terminal_read_context(self):
        ctx = build_context(tool="terminal", command="ls -la")
        assert ctx.action == "read"

    def test_builds_cronjob_context(self):
        ctx = build_context(tool="cronjob", cron_action="create")
        assert ctx.action == "manage"

    def test_resource_falls_back_to_tool(self):
        ctx = build_context(tool="write_file")
        assert ctx.resource == "write_file"

    def test_environment_passed_through(self):
        ctx = build_context(tool="terminal", command="git push", environment="production")
        assert ctx.environment == "production"


# ═════════════════════════════════════════════════════════════════════════════
# Condition helpers
# ═════════════════════════════════════════════════════════════════════════════


class TestConditionHelpers:
    def test_has_lock_true(self):
        assert has_lock(PolicyContext(has_governance_lock=True)) is True

    def test_has_lock_false(self):
        assert has_lock(PolicyContext(has_governance_lock=False)) is False

    def test_not_has_lock_true(self):
        assert not_has_lock(PolicyContext(has_governance_lock=False)) is True

    def test_not_has_lock_false(self):
        assert not_has_lock(PolicyContext(has_governance_lock=True)) is False

    def test_is_production_true(self):
        assert is_production(PolicyContext(environment="production")) is True

    def test_is_production_false(self):
        assert is_production(PolicyContext(environment="development")) is False

    def test_is_confidential_true(self):
        assert is_confidential(PolicyContext(resource_classification="confidential")) is True
        assert is_confidential(PolicyContext(resource_classification="pii")) is True
        assert is_confidential(PolicyContext(resource_classification="restricted")) is True

    def test_is_confidential_false(self):
        assert is_confidential(PolicyContext(resource_classification="public")) is False
        assert is_confidential(PolicyContext(resource_classification="internal")) is False

    def test_during_business_hours(self):
        ctx = PolicyContext(time="2026-07-10T14:00:00")
        assert during_business_hours(ctx) is True

    def test_outside_business_hours(self):
        ctx = PolicyContext(time="2026-07-10T22:00:00")
        assert during_business_hours(ctx) is False


# ═════════════════════════════════════════════════════════════════════════════
# Integration scenarios
# ═════════════════════════════════════════════════════════════════════════════


class TestPolicyIntegration:
    """Real-world policy scenarios."""

    def test_deny_guest_writes_even_with_lock(self):
        """Guests should never write, even with a governance lock."""
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.DENY,
            subject="guest",
            action="write",
            description="Guests cannot write",
            priority=20,
        ))
        ctx = PolicyContext(agent="guest", action="write", has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.DENY

    def test_deny_confidential_resource_writes(self):
        """Confidential resources always need explicit approval."""
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.REQUIRE_APPROVAL,
            subject="*",
            action="write",
            resource="*",
            condition=lambda ctx: is_confidential(ctx),
            description="Confidential data requires approval",
            priority=20,
        ))
        ctx = PolicyContext(agent="titus", action="write", resource_classification="confidential",
                            has_governance_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.REQUIRE_APPROVAL

    def test_titus_can_write_locked(self):
        """Default behavior: Titus with lock can write."""
        engine = PolicyEngine()
        ctx = build_context(tool="write_file", agent="titus", has_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.ALLOW

    def test_titus_cannot_write_unlocked(self):
        """Default behavior: Titus without lock cannot write."""
        engine = PolicyEngine()
        ctx = build_context(tool="write_file", agent="titus", has_lock=False)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.DENY

    def test_read_always_allowed(self):
        """Read operations always pass."""
        engine = PolicyEngine()
        ctx = build_context(tool="read_file", agent="guest", has_lock=False)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.ALLOW

    def test_production_deploy_requires_approval(self):
        """Deploying to production needs two-person approval."""
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.REQUIRE_APPROVAL,
            subject="*",
            action="write",
            condition=lambda ctx: ctx.environment == "production",
            description="Prod deploy requires approval",
            priority=20,
        ))
        ctx = build_context(tool="terminal", agent="dev", command="git push", environment="production",
                            has_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.REQUIRE_APPROVAL

    def test_non_production_deploy_allowed(self):
        """Deploying to dev is fine with lock."""
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            effect=PolicyEffect.REQUIRE_APPROVAL,
            subject="*",
            action="manage",
            condition=lambda ctx: ctx.environment == "production",
            description="Prod deploy requires approval",
            priority=20,
        ))
        ctx = build_context(tool="terminal", agent="dev", command="git push", environment="development",
                            has_lock=True)
        result = engine.evaluate(ctx)
        assert result.effect == PolicyEffect.ALLOW
