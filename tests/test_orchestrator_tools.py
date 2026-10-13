"""
Tests for SafeAgentOrchestrator integration with Phase 4 Tools and Confirmation Flow.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.adapter.llm_client import InferenceMetrics
from src.agent.audit_log import AuditLogger
from src.agent.orchestrator import SafeAgentOrchestrator
from src.agent.policy_engine import PolicyEngine
from src.agent.tools.handlers.tasks import TaskManager
from src.memory.store import MemoryStore


def make_metrics():
    m = InferenceMetrics()
    m.tokens_per_second = 55.0
    m.total_generation_time = 0.3
    m.prompt_tokens = 110
    m.completion_tokens = 25
    return m


def test_orchestrator_task_creation_and_listing(tmp_path: Path):
    db_path = tmp_path / "test_orch.db"
    log_dir = tmp_path / "logs"

    mock_llm = MagicMock()
    policy = PolicyEngine()
    audit = AuditLogger(log_dir)
    task_mgr = TaskManager(db_path=db_path)

    orchestrator = SafeAgentOrchestrator(
        llm_client=mock_llm,
        policy_engine=policy,
        audit_logger=audit,
        task_manager=task_mgr,
    )

    # 1. Create task tool call
    mock_llm.chat_completion.return_value = (
        '{"action": "create_task", "parameters": {"title": "Write report", "due_date": "tomorrow"}}',
        make_metrics(),
    )
    resp1, _ = orchestrator.handle_user_input("Create a task to write report tomorrow.")
    assert "task #1" in resp1.lower()
    assert "created" in resp1.lower()
    assert "write report" in resp1.lower()

    # 2. List tasks tool call
    mock_llm.chat_completion.return_value = (
        '{"action": "list_tasks"}',
        make_metrics(),
    )
    resp2, _ = orchestrator.handle_user_input("What tasks do I have?")
    assert "1 tasks" in resp2.lower()
    assert "write report" in resp2.lower()


def test_orchestrator_app_launch_and_diagnostics(tmp_path: Path):
    db_path = tmp_path / "test_orch.db"
    log_dir = tmp_path / "logs"

    mock_llm = MagicMock()
    policy = PolicyEngine()
    audit = AuditLogger(log_dir)

    orchestrator = SafeAgentOrchestrator(
        llm_client=mock_llm,
        policy_engine=policy,
        audit_logger=audit,
    )

    # Launch application (mocked)
    mock_llm.chat_completion.return_value = (
        '{"action": "launch_application", "parameters": {"app_name": "notepad", "mock_for_test": true}}',
        make_metrics(),
    )
    resp1, _ = orchestrator.handle_user_input("Open Notepad.")
    assert "launched" in resp1.lower()
    assert "notepad" in resp1.lower()

    # Ping router
    mock_llm.chat_completion.return_value = (
        '{"action": "ping_host", "parameters": {"host": "127.0.0.1", "count": 1}}',
        make_metrics(),
    )
    resp2, _ = orchestrator.handle_user_input("Check ping to 127.0.0.1.")
    assert "reachable" in resp2.lower()


def test_orchestrator_two_turn_confirmation_flow(tmp_path: Path):
    db_path = tmp_path / "test_orch.db"
    log_dir = tmp_path / "logs"

    mock_llm = MagicMock()
    policy = PolicyEngine()
    audit = AuditLogger(log_dir)

    orchestrator = SafeAgentOrchestrator(
        llm_client=mock_llm,
        policy_engine=policy,
        audit_logger=audit,
    )

    # Turn 1: Model proposes text insertion (unconfirmed)
    mock_llm.chat_completion.return_value = (
        '{"action": "insert_text", "parameters": {"text": "Hello world", "mock_for_test": true}}',
        make_metrics(),
    )
    resp1, _ = orchestrator.handle_user_input("Type Hello world into the active application.")
    # Assistant asks for confirmation
    assert "confirm" in resp1.lower()
    assert orchestrator.pending_confirmation is not None

    # Turn 2: User responds "yes"
    resp2, _ = orchestrator.handle_user_input("Yes, please proceed.")
    assert orchestrator.pending_confirmation is None
    assert "successfully" in resp2.lower() or "typed" in resp2.lower()


def test_orchestrator_confirmation_cancellation_flow(tmp_path: Path):
    db_path = tmp_path / "test_orch.db"
    log_dir = tmp_path / "logs"

    mock_llm = MagicMock()
    policy = PolicyEngine()
    audit = AuditLogger(log_dir)

    orchestrator = SafeAgentOrchestrator(
        llm_client=mock_llm,
        policy_engine=policy,
        audit_logger=audit,
    )

    # Turn 1: Model proposes text insertion
    mock_llm.chat_completion.return_value = (
        '{"action": "insert_text", "parameters": {"text": "Confidential text", "mock_for_test": true}}',
        make_metrics(),
    )
    resp1, _ = orchestrator.handle_user_input("Type confidential text.")
    assert orchestrator.pending_confirmation is not None

    # Turn 2: User cancels with "no"
    resp2, _ = orchestrator.handle_user_input("No, cancel that.")
    assert orchestrator.pending_confirmation is None
    assert "cancelled" in resp2.lower()
