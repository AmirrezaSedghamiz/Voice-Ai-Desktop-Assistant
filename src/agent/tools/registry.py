"""
Central Tool Registry: Manages registration, argument schema validation,
timeout enforcement, and controlled execution of tool handlers.
"""

from __future__ import annotations

import concurrent.futures
import inspect
import logging
import threading
from typing import Any
from pydantic import BaseModel, ValidationError

from src.agent.tools.models import (
    ExecutionStatus,
    RiskLevel,
    ToolDefinition,
    ToolResult,
)

logger = logging.getLogger("assistant.tools.registry")


class ToolRegistry:
    """Central registry of strictly approved and schema-validated tools."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._lock = threading.Lock()

    def register(self, tool: ToolDefinition) -> None:
        """Registers a tool in the catalog. Overwriting is disallowed to prevent spoofing."""
        with self._lock:
            name = tool.name.strip().lower()
            if name in self._tools:
                raise ValueError(f"Tool '{name}' is already registered in registry.")
            self._tools[name] = tool
            logger.debug("Registered tool: %s (%s)", name, tool.risk_level.value)

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Retrieves a registered tool by case-insensitive name."""
        with self._lock:
            return self._tools.get(name.strip().lower())

    def has_tool(self, name: str) -> bool:
        """Checks if a tool name is registered."""
        with self._lock:
            return name.strip().lower() in self._tools

    def list_tools(self) -> list[ToolDefinition]:
        """Returns all registered tool definitions."""
        with self._lock:
            return list(self._tools.values())

    def validate_arguments(self, name: str, raw_params: dict[str, Any]) -> tuple[bool, dict[str, Any], str | None]:
        """
        Validates raw parameter dictionary against the tool's parameter schema.
        Returns (is_valid, validated_params, error_message).
        """
        tool = self.get_tool(name)
        if not tool:
            return False, {}, f"Tool '{name}' is not registered."

        schema = tool.parameters_schema
        if schema in (dict, None):
            return True, raw_params, None

        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                validated = schema(**raw_params)
                return True, validated.model_dump(), None
            except ValidationError as e:
                errors = "; ".join(f"{err['loc']}: {err['msg']}" for err in e.errors())
                return False, {}, f"Parameter validation error: {errors}"

        return True, raw_params, None

    def execute(
        self,
        name: str,
        parameters: dict[str, Any] | None = None,
        cancellation_token: threading.Event | None = None,
    ) -> ToolResult:
        """
        Executes a registered tool handler with argument validation and timeout enforcement.
        Never executes unregistered tools.
        """
        tool = self.get_tool(name)
        if not tool:
            return ToolResult.fail(
                error=f"Unregistered tool: '{name}' does not exist in the approved tool catalog.",
                details={"action": name},
            )

        params = parameters or {}
        valid, validated_params, err_msg = self.validate_arguments(name, params)
        if not valid:
            return ToolResult.fail(
                error=err_msg or "Invalid tool arguments.",
                details={"action": name, "raw_params": params},
            )

        if cancellation_token and cancellation_token.is_set():
            return ToolResult(
                success=False,
                status=ExecutionStatus.CANCELLED,
                result={},
                error="Operation was cancelled prior to execution.",
            )

        # Inspect handler signature to pass cancellation_token if supported
        call_kwargs = dict(validated_params)
        sig = inspect.signature(tool.handler)
        if "cancellation_token" in sig.parameters:
            call_kwargs["cancellation_token"] = cancellation_token

        timeout = tool.timeout_seconds

        def _run() -> ToolResult:
            try:
                res = tool.handler(**call_kwargs)
                if isinstance(res, ToolResult):
                    return res
                if isinstance(res, dict):
                    success = res.get("status") not in ("error", "failed", "blocked")
                    status = ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED
                    err = res.get("message") if not success else None
                    return ToolResult(success=success, status=status, result=res, error=err)
                return ToolResult.ok(result={"output": res})
            except Exception as e:
                logger.error("Handler error executing '%s': %s", name, e, exc_info=True)
                return ToolResult.fail(error=f"Execution error in '{name}': {str(e)}")

        # Execute with strict timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            try:
                result = future.result(timeout=timeout)
                return result
            except concurrent.futures.TimeoutError:
                logger.warning("Tool '%s' exceeded timeout of %.1fs", name, timeout)
                if cancellation_token:
                    cancellation_token.set()
                return ToolResult.fail(
                    error=f"Tool '{name}' timed out after {timeout:.1f} seconds.",
                    details={"timeout_seconds": timeout},
                )
            except Exception as e:
                return ToolResult.fail(error=f"Tool execution failure: {str(e)}")
