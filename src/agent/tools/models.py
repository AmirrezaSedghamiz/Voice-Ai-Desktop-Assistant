"""
Data models and schemas for the controlled tool-execution system.
Defines risk levels, execution states, tool results, and tool definitions.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    """Permission and risk classification for registered tools."""
    SAFE_READ = "safe_read"                    # Read-only, zero side effects
    SAFE_WRITE = "safe_write"                  # Safe internal side effects (e.g. task creation)
    CONFIRMATION_REQUIRED = "confirmation"      # External side effects requiring explicit user approval
    ADMIN_DENIED = "admin_denied"              # Requires elevation; strictly forbidden offline


class ExecutionStatus(str, Enum):
    """Lifecycle states for tool execution."""
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolResult(BaseModel):
    """Structured result returned by every tool handler."""
    success: bool = Field(..., description="Whether the requested operation succeeded.")
    status: ExecutionStatus = Field(default=ExecutionStatus.COMPLETED, description="Execution status.")
    result: dict[str, Any] = Field(default_factory=dict, description="Validated operation output.")
    error: str | None = Field(default=None, description="Safe, user-readable error message if failed.")
    details: dict[str, Any] | None = Field(default=None, description="Diagnostic information where useful.")

    @classmethod
    def ok(cls, result: dict[str, Any], details: dict[str, Any] | None = None) -> ToolResult:
        """Helper to create a successful completed result."""
        return cls(success=True, status=ExecutionStatus.COMPLETED, result=result, details=details)

    @classmethod
    def fail(cls, error: str, details: dict[str, Any] | None = None) -> ToolResult:
        """Helper to create a failed result."""
        return cls(success=False, status=ExecutionStatus.FAILED, result={}, error=error, details=details)

    @classmethod
    def needs_confirmation(cls, action_name: str, parameters: dict[str, Any], prompt: str) -> ToolResult:
        """Helper to create an awaiting_confirmation result."""
        return cls(
            success=False,
            status=ExecutionStatus.AWAITING_CONFIRMATION,
            result={"action": action_name, "parameters": parameters, "confirmation_prompt": prompt},
            error=None,
            details={"requires_confirmation": True},
        )


class ToolDefinition(BaseModel):
    """Metadata and execution specification for a registered tool."""
    name: str = Field(..., description="Unique, stable identifier for the tool.")
    description: str = Field(..., description="Human-readable description of what the tool does.")
    parameters_schema: Any = Field(default=dict, description="Pydantic model or schema for argument validation.")
    risk_level: RiskLevel = Field(default=RiskLevel.SAFE_READ, description="Risk and permission classification.")
    requires_confirmation: bool = Field(default=False, description="Whether explicit user confirmation is needed before running.")
    supports_cancellation: bool = Field(default=False, description="Whether the handler supports cancellation tokens.")
    timeout_seconds: float = Field(default=15.0, ge=0.5, le=120.0, description="Max execution timeout in seconds.")
    handler: Any = Field(..., description="Callable executing the operation.")

    model_config = ConfigDict(arbitrary_types_allowed=True)
