"""
Agent Orchestrator: Connects the language model, policy engine, tool executor,
resource governor, and local audit logger.
"""

import json
import logging
from typing import Any
import psutil

from src.adapter.llm_client import LocalLlmClient, InferenceMetrics
from src.agent.audit_log import AuditLogger
from src.agent.policy_engine import PolicyEngine
from src.core.governor import ResourceGovernor

logger = logging.getLogger("assistant.orchestrator")

SYSTEM_PROMPT = """You are a helpful, secure, resource-constrained Windows local desktop AI assistant.
You operate completely offline.
When answering conversational questions, be direct, concise, and accurate.
You must never request or attempt shell commands, external network connections, or administrative system changes.
If asked for system diagnostic information, you can propose calling one of these safe tools in JSON format:
- get_system_status
- get_battery_status
- get_resource_metrics
"""


class SafeToolRegistry:
    """Safe, schema-validated tool implementations with bounded scopes."""

    @staticmethod
    def get_system_status() -> dict[str, Any]:
        """Returns non-sensitive host system summary."""
        mem = psutil.virtual_memory()
        return {
            "status": "healthy",
            "cpu_count": psutil.cpu_count(logical=True),
            "ram_used_gb": round((mem.total - mem.available) / (1024**3), 2),
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "ram_percent": mem.percent,
        }

    @staticmethod
    def get_battery_status() -> dict[str, Any]:
        """Returns laptop battery percentage and charging state."""
        battery = psutil.sensors_battery()
        if battery is None:
            return {"battery_present": False, "percent": 100, "power_plugged": True}
        return {
            "battery_present": True,
            "percent": battery.percent,
            "power_plugged": battery.power_plugged,
            "seconds_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else "unlimited",
        }

    @staticmethod
    def get_resource_metrics() -> dict[str, Any]:
        """Returns current CPU and RAM load."""
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "virtual_memory_percent": psutil.virtual_memory().percent,
        }


class SafeAgentOrchestrator:
    """Coordinates model proposal, policy enforcement, execution, and audit logging."""

    def __init__(
        self,
        llm_client: LocalLlmClient,
        policy_engine: PolicyEngine,
        audit_logger: AuditLogger,
        governor: ResourceGovernor | None = None,
    ):
        self.llm_client = llm_client
        self.policy_engine = policy_engine
        self.audit_logger = audit_logger
        self.governor = governor
        self.tools = SafeToolRegistry()
        self.conversation_history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def reset_conversation(self) -> None:
        """Clears conversational turns back to system prompt."""
        self.conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def handle_user_input(self, user_text: str) -> tuple[str, InferenceMetrics]:
        """Processes a user input turn through the policy and inference pipeline."""
        if self.governor:
            self.governor.touch_activity()

        self.conversation_history.append({"role": "user", "content": user_text})

        # Generate response from local LLM
        response_text, metrics = self.llm_client.chat_completion(self.conversation_history)

        proposed_action = None
        policy_decision = "PERMITTED"
        policy_reason = "Conversational output"

        # Check if the model attempted a tool call formatted as JSON
        if "{" in response_text and "}" in response_text:
            try:
                candidate = response_text[response_text.find("{"):response_text.rfind("}") + 1]
                data = json.loads(candidate)
                if "action" in data:
                    proposed_action = data
                    action_name = data.get("action", "")
                    eval_result = self.policy_engine.evaluate(action_name, data.get("parameters"))

                    if eval_result.allowed:
                        policy_decision = "PERMITTED"
                        policy_reason = eval_result.reason
                        # Execute safe tool
                        tool_func = getattr(self.tools, action_name, None)
                        if tool_func:
                            tool_result = tool_func()
                            response_text += f"\n\n[Tool Output ({action_name})]: {json.dumps(tool_result)}"
                    else:
                        policy_decision = "BLOCKED"
                        policy_reason = eval_result.reason
                        response_text = f"[POLICY BLOCK] Prohibited action requested: {eval_result.reason}"
            except Exception:
                pass  # Regular text containing braces

        self.conversation_history.append({"role": "assistant", "content": response_text})

        # Record event in local audit log
        self.audit_logger.log_event(
            event_type="chat_turn",
            user_input=user_text,
            proposed_action=proposed_action,
            policy_decision=policy_decision,
            policy_reason=policy_reason,
            model_output=response_text,
            metrics={
                "tps": round(metrics.tokens_per_second, 2),
                "total_time_s": round(metrics.total_generation_time, 2),
                "prompt_tokens": metrics.prompt_tokens,
                "completion_tokens": metrics.completion_tokens,
            },
        )

        return response_text, metrics
