"""
Agent Orchestrator: Connects the language model, policy engine, tool executor,
resource governor, and local audit logger.
"""

import json
import logging
import re
from typing import Any
import psutil

from src.adapter.llm_client import LocalLlmClient, InferenceMetrics
from src.agent.audit_log import AuditLogger
from src.agent.policy_engine import PolicyEngine
from src.core.governor import ResourceGovernor

logger = logging.getLogger("assistant.orchestrator")

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # geometric shapes extended
    "\U0001F800-\U0001F8FF"  # supplemental arrows-C
    "\U0001F900-\U0001F9FF"  # supplemental symbols and pictographs
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
    "\u2600-\u26FF"          # misc symbols
    "\u2700-\u27BF"          # dingbats
    "\uFE00-\uFE0F"          # variation selectors
    "\u200d"                 # zero width joiner
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Removes all Unicode emojis and decorative pictographs from text."""
    if not text:
        return ""
    cleaned = EMOJI_PATTERN.sub("", text)
    return re.sub(r" {2,}", " ", cleaned).strip()


SYSTEM_PROMPT = """/no_think
You are a helpful, secure, resource-constrained Windows local desktop AI assistant running on the local Qwen3-1.7B model.
You operate completely offline.

STYLE AND VOICE RULES:
- NEVER use emojis, emoticons, or decorative symbols in any response.
- Be direct, concise, and natural so your responses sound clean when spoken aloud.

MEMORY AND CONTEXT RULES:
- You have full access to the current conversation history in this session.
- Always use earlier messages in the conversation to remember the user's name, corrections, preferences, and prior topics.
- If the user spells out a name or word (even if speech-to-text transcribes the letters phonetically, such as "AMIR or EZA" and "SE DG H-A-M-I"), reconstruct the spelled letters into the proper name (e.g., Amirreza Sedghamiz).
- NEVER say "I don't have memory of previous interactions" or claim you cannot remember earlier turns in this conversation.

TOOL CALLING RULES:
- Never request or attempt shell commands, external network connections, or administrative system changes.
- When the user asks for their laptop battery status/percentage, system hardware summary, or current CPU/RAM load, respond ONLY with a single JSON object in this exact format and nothing else (NEVER invent or include a "result" field):
{"action": "get_battery_status"}
{"action": "get_system_status"}
{"action": "get_resource_metrics"}
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
            "percent": round(battery.percent),
            "power_plugged": bool(battery.power_plugged),
            "seconds_left": (
                battery.secsleft
                if battery.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
                else "unlimited"
            ),
        }

    @staticmethod
    def get_resource_metrics() -> dict[str, Any]:
        """Returns current CPU and RAM load."""
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "virtual_memory_percent": psutil.virtual_memory().percent,
        }

    @staticmethod
    def format_tool_result(action_name: str, result: dict[str, Any]) -> str:
        """Converts raw tool dictionary output into a natural spoken sentence."""
        if action_name == "get_battery_status":
            if not result.get("battery_present", True):
                return "No battery was detected. Your system is running on direct AC power."
            pct = result.get("percent", 0)
            plugged = result.get("power_plugged", False)
            state = "plugged into power" if plugged else "running on battery power"
            secs = result.get("seconds_left")
            if not plugged and isinstance(secs, (int, float)) and secs > 0:
                mins = int(secs // 60)
                return f"Your laptop battery is at {pct}% and {state}, with approximately {mins} minutes remaining."
            return f"Your laptop battery is at {pct}% and {state}."

        if action_name == "get_system_status":
            return (
                f"Your system status is {result.get('status', 'healthy')}. "
                f"It has {result.get('cpu_count')} logical CPU cores, and memory usage is at "
                f"{result.get('ram_used_gb')} gigabytes out of {result.get('ram_total_gb')} gigabytes "
                f"({result.get('ram_percent')}%)."
            )

        if action_name == "get_resource_metrics":
            return (
                f"Current CPU load is {result.get('cpu_percent')}%, and RAM usage is at "
                f"{result.get('virtual_memory_percent')}%."
            )

        # Fallback for any other tool
        parts = [f"{k.replace('_', ' ')} is {v}" for k, v in result.items()]
        return "Here is the requested information: " + ", ".join(parts) + "."


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
        raw_response, metrics = self.llm_client.chat_completion(self.conversation_history)
        response_text = strip_emojis(raw_response)

        proposed_action = None
        policy_decision = "PERMITTED"
        policy_reason = "Conversational output"

        # Check if the model attempted a tool call formatted as JSON (supports both "action" and "tool" keys)
        if "{" in response_text and "}" in response_text:
            try:
                candidate = response_text[response_text.find("{") : response_text.rfind("}") + 1]
                data = json.loads(candidate)
                if isinstance(data, dict) and ("action" in data or "tool" in data):
                    action_name = str(data.get("action") or data.get("tool") or "").strip()
                    parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else None
                    proposed_action = {"action": action_name, "parameters": parameters}

                    eval_result = self.policy_engine.evaluate(action_name, parameters)

                    if eval_result.allowed:
                        policy_decision = "PERMITTED"
                        policy_reason = eval_result.reason
                        # Execute real safe tool (ignoring any hallucinated "result" field from LLM)
                        tool_func = getattr(self.tools, action_name, None)
                        if tool_func:
                            tool_result = tool_func()
                            response_text = self.tools.format_tool_result(action_name, tool_result)
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
