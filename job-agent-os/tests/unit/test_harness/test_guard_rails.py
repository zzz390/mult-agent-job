"""Unit tests for Guard Rails."""

import pytest

from job_agent_os.harness.guard_rails import (
    GuardRailChain,
    GuardRailViolation,
    LoopDetectionGuard,
    OutputValidationGuard,
    StepLimitGuard,
    TokenBudgetGuard,
)


class TestTokenBudgetGuard:
    """Test TokenBudgetGuard."""

    def test_within_budget_passes(self):
        """Should not raise when within budget."""
        guard = TokenBudgetGuard(max_tokens=1000)
        guard.add_usage(500)
        # Should not raise
        guard.before_node("test_node", {})

    def test_exceeds_budget_raises(self):
        """Should raise GuardRailViolation when budget exceeded."""
        guard = TokenBudgetGuard(max_tokens=1000)
        guard.add_usage(1000)
        with pytest.raises(GuardRailViolation) as exc_info:
            guard.before_node("test_node", {})
        assert "token_budget" in str(exc_info.value)
        assert "1000/1000" in str(exc_info.value)

    def test_after_node_tracks_usage(self):
        """after_node should extract token usage from result."""
        guard = TokenBudgetGuard(max_tokens=10000)
        result = {"token_usage": {"total_tokens": 500}}
        guard.after_node("test_node", {}, result)
        assert guard.tokens_used == 500

    def test_after_node_no_token_usage(self):
        """after_node should handle missing token_usage gracefully."""
        guard = TokenBudgetGuard(max_tokens=10000)
        guard.after_node("test_node", {}, {"other_key": "value"})
        assert guard.tokens_used == 0

    def test_usage_ratio(self):
        """Test usage_ratio property."""
        guard = TokenBudgetGuard(max_tokens=1000)
        guard.add_usage(250)
        assert guard.usage_ratio == 0.25

    def test_reset(self):
        """Reset should clear token count."""
        guard = TokenBudgetGuard(max_tokens=1000)
        guard.add_usage(500)
        guard.reset()
        assert guard.tokens_used == 0


class TestStepLimitGuard:
    """Test StepLimitGuard."""

    def test_within_limit_passes(self):
        """Should not raise when within step limit."""
        guard = StepLimitGuard(max_steps=10)
        for _ in range(5):
            guard.before_node("node", {})
            guard.after_node("node", {}, {})

    def test_exceeds_limit_raises(self):
        """Should raise when step limit exceeded."""
        guard = StepLimitGuard(max_steps=3)
        for _ in range(3):
            guard.before_node("node", {})
            guard.after_node("node", {}, {})

        with pytest.raises(GuardRailViolation) as exc_info:
            guard.before_node("node", {})
        assert "step_limit" in str(exc_info.value)
        assert "3/3" in str(exc_info.value)

    def test_step_count_increments(self):
        """Step count should increment on after_node."""
        guard = StepLimitGuard(max_steps=100)
        assert guard.step_count == 0
        guard.after_node("node", {}, {})
        assert guard.step_count == 1
        guard.after_node("node", {}, {})
        assert guard.step_count == 2

    def test_reset(self):
        """Reset should clear step count."""
        guard = StepLimitGuard(max_steps=10)
        guard.after_node("node", {}, {})
        guard.after_node("node", {}, {})
        guard.reset()
        assert guard.step_count == 0


class TestLoopDetectionGuard:
    """Test LoopDetectionGuard."""

    def test_no_loop_passes(self):
        """Different nodes should not trigger loop detection."""
        guard = LoopDetectionGuard(threshold=3)
        guard.before_node("node_a", {})
        guard.before_node("node_b", {})
        guard.before_node("node_c", {})
        # No exception should be raised

    def test_loop_detected_raises(self):
        """Same node repeated beyond threshold should raise."""
        guard = LoopDetectionGuard(threshold=3)
        # First 3 calls are OK (threshold = 3, triggers on > 3)
        guard.before_node("stuck_node", {})
        guard.before_node("stuck_node", {})
        guard.before_node("stuck_node", {})

        with pytest.raises(GuardRailViolation) as exc_info:
            guard.before_node("stuck_node", {})
        assert "loop_detection" in str(exc_info.value)
        assert "stuck_node" in str(exc_info.value)

    def test_different_nodes_independent(self):
        """Each node has independent counter."""
        guard = LoopDetectionGuard(threshold=2)
        guard.before_node("node_a", {})
        guard.before_node("node_a", {})
        guard.before_node("node_b", {})
        guard.before_node("node_b", {})
        # node_a at 2, node_b at 2, threshold is 2, next call triggers
        with pytest.raises(GuardRailViolation):
            guard.before_node("node_a", {})

    def test_reset(self):
        """Reset should clear all node counts."""
        guard = LoopDetectionGuard(threshold=2)
        guard.before_node("node_a", {})
        guard.before_node("node_a", {})
        guard.reset()
        # Should not raise after reset
        guard.before_node("node_a", {})
        guard.before_node("node_a", {})


class TestOutputValidationGuard:
    """Test OutputValidationGuard."""

    def test_valid_dict_output_passes(self):
        """Dict output should pass validation."""
        guard = OutputValidationGuard()
        # Should not raise
        guard.after_node("node", {}, {"current_phase": "intent"})

    def test_non_dict_output_raises(self):
        """Non-dict output should raise."""
        guard = OutputValidationGuard()
        with pytest.raises(GuardRailViolation) as exc_info:
            guard.after_node("node", {}, "not a dict")
        assert "output_validation" in str(exc_info.value)

    def test_list_output_raises(self):
        """List output should raise."""
        guard = OutputValidationGuard()
        with pytest.raises(GuardRailViolation):
            guard.after_node("node", {}, [1, 2, 3])


class TestGuardRailChain:
    """Test GuardRailChain middleware."""

    def test_chain_runs_all_guards(self):
        """Chain should run all guards in sequence."""
        guards = [
            TokenBudgetGuard(max_tokens=10000),
            StepLimitGuard(max_steps=100),
            LoopDetectionGuard(threshold=10),
        ]
        chain = GuardRailChain(guards=guards)

        # Should not raise
        chain.before_node("test", {})
        chain.after_node("test", {}, {"token_usage": {"total_tokens": 100}})

    def test_chain_stops_on_first_violation(self):
        """Chain should stop at first violation."""
        step_guard = StepLimitGuard(max_steps=1)
        step_guard.after_node("node", {}, {})  # step_count = 1, now at limit
        guards = [
            step_guard,  # Will violate on next before_node
            TokenBudgetGuard(max_tokens=10000),
        ]
        chain = GuardRailChain(guards=guards)

        with pytest.raises(GuardRailViolation):
            chain.before_node("test", {})

    def test_get_guard_by_name(self):
        """Should retrieve guard by name."""
        chain = GuardRailChain()
        token_guard = chain.get_guard("token_budget")
        assert token_guard is not None
        assert token_guard.name == "token_budget"

    def test_get_guard_not_found(self):
        """Should return None for unknown guard name."""
        chain = GuardRailChain()
        assert chain.get_guard("nonexistent") is None

    def test_reset_all_guards(self):
        """Reset should reset all guards in chain."""
        chain = GuardRailChain()
        # Simulate some usage
        chain.after_node("node", {}, {"token_usage": {"total_tokens": 500}})
        chain.reset()

        token_guard = chain.get_guard("token_budget")
        step_guard = chain.get_guard("step_limit")
        assert token_guard.tokens_used == 0
        assert step_guard.step_count == 0

    def test_default_guards_created(self):
        """Default chain should have 4 guards."""
        chain = GuardRailChain()
        assert len(chain.guards) == 4


class TestGuardRailViolation:
    """Test GuardRailViolation exception."""

    def test_exception_message_format(self):
        """Exception message should include guard name."""
        exc = GuardRailViolation("test_guard", "something went wrong")
        assert "[test_guard]" in str(exc)
        assert "something went wrong" in str(exc)
        assert exc.guard_name == "test_guard"
