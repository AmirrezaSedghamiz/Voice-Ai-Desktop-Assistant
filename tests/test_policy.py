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


def test_orchestrator_emoji_stripping_and_tool_execution(tmp_path):
    from unittest.mock import MagicMock, patch
    from src.adapter.llm_client import InferenceMetrics
    from src.agent.audit_log import AuditLogger
    from src.agent.orchestrator import SafeAgentOrchestrator, strip_emojis

    assert strip_emojis("Have a great day! 😊🚀✨") == "Have a great day!"

    mock_client = MagicMock()
    metrics = InferenceMetrics()
    metrics.tokens_per_second = 55.0
    metrics.total_generation_time = 0.5
    metrics.prompt_tokens = 50
    metrics.completion_tokens = 20

    # Simulate the LLM returning "tool" instead of "action" AND a hallucinated "result" + emoji
    mock_client.chat_completion.return_value = (
        '{\n  "tool": "get_battery_status",\n  "result": "Battery percentage: 65%"\n} 😊',
        metrics,
    )

    orchestrator = SafeAgentOrchestrator(
        llm_client=mock_client,
        policy_engine=PolicyEngine(),
        audit_logger=AuditLogger(tmp_path),
    )

    with patch.object(
        orchestrator.tools,
        "get_battery_status",
        return_value={"battery_present": True, "percent": 100, "power_plugged": True, "seconds_left": "unlimited"},
    ):
        response, _ = orchestrator.handle_user_input("What is my battery percentage?")

    assert "100%" in response
    assert "plugged into power" in response
    assert "65%" not in response
    assert "{" not in response
    assert "😊" not in response

