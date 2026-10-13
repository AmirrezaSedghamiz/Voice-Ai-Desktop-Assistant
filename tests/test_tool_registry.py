"""
Unit tests for ToolRegistry, ToolDefinition, ToolResult, and PolicyEngine argument validation.
"""

import threading
import time
from pathlib import Path
import pytest
from pydantic import BaseModel, Field

from src.agent.policy_engine import PolicyEngine
from src.agent.tools.models import ExecutionStatus, RiskLevel, ToolDefinition, ToolResult
from src.agent.tools.registry import ToolRegistry
from src.core.config import PROJECT_ROOT


class EchoParams(BaseModel):
    message: str = Field(..., min_length=1)
    repeat: int = Field(default=1, ge=1, le=5)


def test_tool_registry_registration_and_lookup():
    registry = ToolRegistry()

    def dummy_handler(message: str, repeat: int = 1) -> ToolResult:
        return ToolResult.ok(result={"echo": message * repeat})

    tool = ToolDefinition(
        name="test_echo",
        description="Echoes message.",
        parameters_schema=EchoParams,
        risk_level=RiskLevel.SAFE_READ,
        handler=dummy_handler,
    )

    registry.register(tool)
    assert registry.has_tool("test_echo")
    assert registry.has_tool("TEST_ECHO")  # case-insensitive
    assert registry.get_tool("test_echo") == tool
    assert len(registry.list_tools()) == 1

    # Duplicate registration should raise error
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_tool_registry_execution_and_schema_validation():
    registry = ToolRegistry()

    def dummy_handler(message: str, repeat: int = 1) -> ToolResult:
        return ToolResult.ok(result={"echo": message * repeat})

    tool = ToolDefinition(
        name="test_echo",
        description="Echoes message.",
        parameters_schema=EchoParams,
        risk_level=RiskLevel.SAFE_READ,
        handler=dummy_handler,
    )
    registry.register(tool)

    # Valid execution
    res = registry.execute("test_echo", {"message": "hi", "repeat": 2})
    assert res.success is True
    assert res.status == ExecutionStatus.COMPLETED
    assert res.result["echo"] == "hihi"

    # Invalid parameter types/schema
    res_err = registry.execute("test_echo", {"repeat": 10})  # missing message, repeat > 5
    assert res_err.success is False
    assert res_err.status == ExecutionStatus.FAILED
    assert "Parameter validation error" in res_err.error

    # Unregistered tool
    res_unreg = registry.execute("non_existent_tool")
    assert res_unreg.success is False
    assert "Unregistered tool" in res_unreg.error


def test_tool_registry_timeout_enforcement():
    registry = ToolRegistry()

    def slow_handler() -> ToolResult:
        time.sleep(1.0)
        return ToolResult.ok(result={"done": True})

    tool = ToolDefinition(
        name="slow_tool",
        description="A slow tool.",
        parameters_schema=dict,
        timeout_seconds=0.5,  # Times out after 0.5s
        handler=slow_handler,
    )
    registry.register(tool)

    res = registry.execute("slow_tool")
    assert res.success is False
    assert res.status == ExecutionStatus.FAILED
    assert "timed out" in res.error.lower()


def test_tool_registry_cancellation_support():
    registry = ToolRegistry()

    def cancellable_handler(cancellation_token=None) -> ToolResult:
        if cancellation_token and cancellation_token.is_set():
            return ToolResult(success=False, status=ExecutionStatus.CANCELLED, result={}, error="Cancelled")
        return ToolResult.ok(result={"ok": True})

    tool = ToolDefinition(
        name="cancel_tool",
        description="Cancellable tool.",
        parameters_schema=dict,
        supports_cancellation=True,
        handler=cancellable_handler,
    )
    registry.register(tool)

    token = threading.Event()
    token.set()
    res = registry.execute("cancel_tool", cancellation_token=token)
    assert res.success is False
    assert res.status == ExecutionStatus.CANCELLED


def test_policy_engine_application_allowlist():
    engine = PolicyEngine()

    # Allowed apps
    for app in ["notepad", "calculator", "paint", "explorer"]:
        dec = engine.evaluate("launch_application", {"app_name": app})
        assert dec.allowed is True

    # Forbidden / unapproved apps
    dec_bad = engine.evaluate("launch_application", {"app_name": "cmd.exe"})
    assert dec_bad.allowed is False
    assert "not in the approved allowlist" in dec_bad.reason

    dec_powershell = engine.evaluate("launch_application", {"app_name": "powershell"})
    assert dec_powershell.allowed is False


def test_policy_engine_ping_host_validation():
    engine = PolicyEngine()

    # Valid hosts
    assert engine.evaluate("ping_host", {"host": "127.0.0.1"}).allowed is True
    assert engine.evaluate("ping_host", {"host": "google.com"}).allowed is True
    assert engine.evaluate("ping_host", {"host": "local-router"}).allowed is True

    # Injection attempts
    assert engine.evaluate("ping_host", {"host": "127.0.0.1; whoami"}).allowed is False
    assert engine.evaluate("ping_host", {"host": "127.0.0.1 | dir"}).allowed is False
    assert engine.evaluate("ping_host", {"host": "127.0.0.1 && calc"}).allowed is False
    assert engine.evaluate("ping_host", {"host": "$(id)"}).allowed is False


def test_policy_engine_search_path_confinement(tmp_path):
    auth_root = tmp_path / "authorized_folder"
    auth_root.mkdir()
    engine = PolicyEngine(authorized_roots=[auth_root])

    # Path inside authorized root
    valid_sub = auth_root / "subdir"
    valid_sub.mkdir()
    assert engine.evaluate("search_files", {"root_dir": str(valid_sub)}).allowed is True

    # Path outside authorized root (traversal)
    outside = tmp_path / "outside_folder"
    outside.mkdir()
    dec_out = engine.evaluate("search_files", {"root_dir": str(outside)})
    assert dec_out.allowed is False
    assert "outside authorized search roots" in dec_out.reason

    # Traversal attempt via ..
    traversal_attempt = str(auth_root / ".." / "outside_folder")
    dec_trav = engine.evaluate("search_files", {"root_dir": traversal_attempt})
    assert dec_trav.allowed is False

    # System directory forbidden check
    dec_sys = engine.evaluate("search_files", {"root_dir": r"C:\Windows\System32"})
    assert dec_sys.allowed is False
