"""
Tests for Policy Engine authorization and dangerous tool blocking.
"""

from src.agent.policy_engine import PolicyEngine


def test_conversational_turn_permitted():
    engine = PolicyEngine()
    decision = engine.evaluate(action_name="", parameters=None)
    assert decision.allowed is True


def test_whitelisted_tools_permitted():
    engine = PolicyEngine()
    for tool_name in ["get_system_status", "get_battery_status", "get_resource_metrics"]:
        decision = engine.evaluate(action_name=tool_name)
        assert decision.allowed is True
        assert "authorized" in decision.reason


def test_dangerous_actions_blocked():
    engine = PolicyEngine()
    dangerous = [
        "execute_shell",
        "execute_powershell",
        "execute_cmd",
        "run_terminal_command",
        "delete_file",
        "modify_registry",
        "access_internet",
        "powershell_script",
        "exec_calc",
    ]
    for action in dangerous:
        decision = engine.evaluate(action_name=action)
        assert decision.allowed is False
        assert "forbidden" in decision.reason.lower() or "blocked" in decision.reason.lower() or "violation" in decision.reason.lower()


def test_unregistered_actions_blocked():
    engine = PolicyEngine()
    decision = engine.evaluate(action_name="unregistered_random_tool")
    assert decision.allowed is False
    assert "not in the approved tool whitelist" in decision.reason
