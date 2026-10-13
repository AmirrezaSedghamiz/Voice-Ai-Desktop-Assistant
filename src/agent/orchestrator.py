"""
Agent Orchestrator: Connects the language model, policy engine, tool executor,
persistent SQLite memory store, resource governor, and local audit logger.
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
from src.memory.store import MemoryStore, MemoryValidationError, MemoryStoreError

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


def extract_name_from_user_text(text: str) -> str | None:
    """
    Extracts user preferred name from introductory statements in English or Persian.
    Returns cleaned name or None if no introductory pattern is matched.
    """
    if not text or not isinstance(text, str):
        return None

    # Persian patterns: "اسم من ... است/هست", "نام من ... است/هست"
    fa_match = re.search(
        r"(?:اسم من|نام من)\s+([A-Za-z\u0600-\u06FF\s]+?)(?:\s+(?:است|هست)|[\.!\?،,]|$)",
        text,
        re.IGNORECASE,
    )
    if fa_match:
        name = fa_match.group(1).strip()
        if name and len(name) < 50:
            return name

    # English patterns - prioritize corrections and direct statements
    patterns = [
        r"(?:my name is actually|actually my name is)\s+([A-Za-z\u0600-\u06FF\s,]+?)(?:[\.!\?]|You can|\b(?:and|but|i am|who)\b|$)",
        r"(?:my name is|name is|call me|you can call me|i am called)\s+([A-Za-z\u0600-\u06FF\s,]+?)(?:[\.!\?]|You can|\b(?:and|but|i am|who)\b|$)",
    ]
    for pat in patterns:
        matches = list(re.finditer(pat, text, re.IGNORECASE))
        if matches:
            name_raw = matches[-1].group(1).strip()
            # Clean comma-separated tokens often produced by voice STT
            cleaned = re.sub(r"[,]+", " ", name_raw)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned and not cleaned.lower().startswith(("not ", "no ", "a user", "trying")):
                words = cleaned.split()
                if 1 <= len(words) <= 6:
                    return cleaned
    return None


BASE_SYSTEM_PROMPT = """/no_think
You are a helpful, secure, resource-constrained Windows local desktop AI assistant running on the local Qwen3-1.7B model.
You operate completely offline.

STYLE AND VOICE RULES:
- NEVER use emojis, emoticons, or decorative symbols in any response.
- Be direct, concise, and natural so your responses sound clean when spoken aloud.

MEMORY RULES:
- You have persistent memory across restarts.
- If the user asks for their name or if you remember them, use the preferred_name in the memory profile above to answer directly. If no preferred_name is listed, politely ask for their name.
- When the user introduces themselves, output tool call {"action": "remember_fact", "parameters": {"key": "preferred_name", "value": "<name>", "category": "profile"}}.

TOOL CALLING RULES:
- Never request or attempt shell commands, external network connections, raw SQL queries, or administrative system changes.
- CRITICAL: You cannot save or delete memories by replying in plain text. Whenever the user asks you to remember a fact ("remember that..."), forget a fact ("forget..."), save a note ("save a note..."), search saved notes/memories, or check battery/system/resource status, you MUST respond ONLY with a raw JSON object in one of these exact formats and NO other text (NEVER include a "result" field):
- For battery status: {"action": "get_battery_status"}
- For system hardware status: {"action": "get_system_status"}
- For CPU/RAM load: {"action": "get_resource_metrics"}
- To remember a user fact or preference: {"action": "remember_fact", "parameters": {"key": "<short_snake_case_key>", "value": "<fact_value>", "category": "profile"}}
- To search saved memories or notes: {"action": "recall_facts", "parameters": {"query": "<search_keywords>"}}
- To forget/delete a saved fact: {"action": "forget_fact", "parameters": {"key": "<fact_key>"}}
- To save a durable note: {"action": "save_note", "parameters": {"title": "<note_title>", "content": "<note_content>"}}
"""

# Alias preserved for backwards compatibility
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT


class SafeToolRegistry:
    """Safe, schema-validated tool implementations with bounded scopes."""

    def __init__(self, memory_store: MemoryStore | None = None):
        self.memory_store = memory_store

    @staticmethod
    def get_system_status(**kwargs: Any) -> dict[str, Any]:
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
    def get_battery_status(**kwargs: Any) -> dict[str, Any]:
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
    def get_resource_metrics(**kwargs: Any) -> dict[str, Any]:
        """Returns current CPU and RAM load."""
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "virtual_memory_percent": psutil.virtual_memory().percent,
        }

    def remember_fact(
        self,
        key: str = "",
        value: str = "",
        category: str = "profile",
        source: str = "user_explicit",
        allow_overwrite: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Persists a validated user or project fact into local SQLite storage."""
        if self.memory_store is None:
            return {"status": "error", "message": "Persistent memory store is not attached."}
        try:
            res = self.memory_store.remember_fact(
                key=key,
                value=value,
                category=category,
                source=source,
                allow_overwrite=bool(allow_overwrite),
            )
            return {
                "status": res.status,
                "key": res.key,
                "value": res.value,
                "fact_id": res.fact_id,
                "existing_value": res.existing_value,
                "message": res.message,
            }
        except (MemoryValidationError, MemoryStoreError) as e:
            return {"status": "error", "key": str(key), "message": str(e)}

    def recall_facts(self, query: str = "", limit: int = 5, **kwargs: Any) -> dict[str, Any]:
        """Searches saved facts and notes via SQLite FTS5."""
        if self.memory_store is None:
            return {"status": "error", "message": "Persistent memory store is not attached."}
        if not isinstance(query, str) or not query.strip():
            return {"status": "error", "query": "", "results": [], "message": "Search query cannot be empty."}
        try:
            bounded_limit = max(1, min(int(limit), 10))
            hits = self.memory_store.recall_facts(query=query, limit=bounded_limit)
            serialized = [
                {
                    "type": h.record_type,
                    "id": h.id,
                    "key_or_title": h.key_or_title,
                    "content": h.content,
                    "category": h.category,
                    "source": h.source,
                }
                for h in hits
            ]
            return {
                "status": "ok" if serialized else "empty",
                "query": query.strip(),
                "count": len(serialized),
                "results": serialized,
            }
        except (MemoryValidationError, MemoryStoreError, ValueError) as e:
            return {"status": "error", "query": str(query), "results": [], "message": str(e)}

    def forget_fact(self, key: str = "", **kwargs: Any) -> dict[str, Any]:
        """Deactivates an active fact by exact normalized key."""
        if self.memory_store is None:
            return {"status": "error", "message": "Persistent memory store is not attached."}
        try:
            res = self.memory_store.forget_fact(key=key)
            return {
                "status": res.status,
                "key": res.key,
                "candidates": res.candidates,
                "message": res.message,
            }
        except (MemoryValidationError, MemoryStoreError) as e:
            return {"status": "error", "key": str(key), "message": str(e)}

    def save_note(
        self,
        title: str = "",
        content: str = "",
        tags: str = "",
        category: str = "general",
        project: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Saves a durable user note into local SQLite storage and FTS5 index."""
        if self.memory_store is None:
            return {"status": "error", "message": "Persistent memory store is not attached."}
        try:
            note = self.memory_store.save_note(
                title=title,
                content=content,
                tags=tags,
                category=category,
                project=project,
            )
            return {
                "status": "saved",
                "note_id": note.id,
                "title": note.title,
                "category": note.category,
                "message": f"Saved note '{note.title}' (ID: {note.id}).",
            }
        except (MemoryValidationError, MemoryStoreError) as e:
            return {"status": "error", "title": str(title), "message": str(e)}

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

        if action_name == "remember_fact":
            status = result.get("status")
            if status in ("created", "updated", "unchanged"):
                readable_key = str(result.get("key", "")).replace("_", " ")
                return f"I have saved that in my long-term memory: {readable_key} is {result.get('value')}."
            return str(result.get("message", "Could not save that fact."))

        if action_name == "recall_facts":
            status = result.get("status")
            hits = result.get("results", [])
            if status == "ok" and hits:
                items = [
                    f"{h['key_or_title'].replace('_', ' ')}: {h['content']}"
                    for h in hits[:5]
                ]
                return "Here is what I found in your saved memory: " + "; ".join(items) + "."
            if status == "empty":
                return f"I checked my saved memory for {result.get('query', 'that topic')}, but found no matching records."
            return str(result.get("message", "Could not search memory."))

        if action_name == "forget_fact":
            status = result.get("status")
            if status == "deleted":
                readable_key = str(result.get("key", "")).replace("_", " ")
                return f"I have removed {readable_key} from my long-term memory."
            return str(result.get("message", "Could not remove that fact."))

        if action_name == "save_note":
            if result.get("status") == "saved":
                return f"I have saved your note titled {result.get('title')}."
            return str(result.get("message", "Could not save that note."))

        # Fallback for any other tool
        parts = [f"{k.replace('_', ' ')} is {v}" for k, v in result.items()]
        return "Here is the requested information: " + ", ".join(parts) + "."


class SafeAgentOrchestrator:
    """Coordinates model proposal, policy enforcement, execution, profile injection, and audit logging."""

    def __init__(
        self,
        llm_client: LocalLlmClient,
        policy_engine: PolicyEngine,
        audit_logger: AuditLogger,
        governor: ResourceGovernor | None = None,
        memory_store: MemoryStore | None = None,
    ):
        self.llm_client = llm_client
        self.policy_engine = policy_engine
        self.audit_logger = audit_logger
        self.governor = governor
        self.memory_store = memory_store
        self.tools = SafeToolRegistry(memory_store=memory_store)
        self.conversation_history: list[dict[str, str]] = [
            {"role": "system", "content": self.build_system_prompt()}
        ]

    def build_system_prompt(self) -> str:
        """
        Constructs the system prompt by combining trusted system rules with
        the bounded, clearly delimited user profile block.
        Never makes an extra LLM call.
        """
        if self.memory_store is None:
            return BASE_SYSTEM_PROMPT

        try:
            payload = self.memory_store.build_profile_context()
            if payload.formatted_block:
                marker = "You operate completely offline.\n"
                if marker in BASE_SYSTEM_PROMPT:
                    return BASE_SYSTEM_PROMPT.replace(
                        marker,
                        f"{marker}\n{payload.formatted_block}\n",
                        1,
                    )
                return f"{BASE_SYSTEM_PROMPT.rstrip()}\n\n{payload.formatted_block}\n"
        except Exception as e:
            logger.error("Failed to load user profile context from memory store: %s", e)

        return BASE_SYSTEM_PROMPT

    def refresh_system_prompt(self) -> str:
        """Updates the active system message in-place with the latest saved profile facts."""
        updated_prompt = self.build_system_prompt()
        if self.conversation_history and self.conversation_history[0].get("role") == "system":
            self.conversation_history[0]["content"] = updated_prompt
        else:
            self.conversation_history.insert(0, {"role": "system", "content": updated_prompt})
        return updated_prompt

    def reset_conversation(self) -> None:
        """Clears conversational turns back to system prompt while preserving persistent profile facts."""
        self.conversation_history = [{"role": "system", "content": self.build_system_prompt()}]

    def handle_user_input(self, user_text: str) -> tuple[str, InferenceMetrics]:
        """Processes a user input turn through the policy, memory, and inference pipeline."""
        if self.governor:
            self.governor.touch_activity()

        # Deterministic identity capture: ensure user's name is persisted if they introduce themselves
        if self.memory_store is not None:
            detected_name = extract_name_from_user_text(user_text)
            if detected_name:
                try:
                    self.memory_store.remember_fact(
                        key="preferred_name",
                        value=detected_name,
                        category="profile",
                        source="user_explicit",
                        allow_overwrite=True,
                    )
                except Exception as e:
                    logger.warning("Could not auto-persist preferred_name: %s", e)

        # Ensure system prompt reflects current active profile facts
        self.refresh_system_prompt()

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
                    if isinstance(data.get("parameters"), dict):
                        parameters = dict(data["parameters"])
                    else:
                        # Support flattened arguments from compact models (excluding meta keys)
                        parameters = {
                            k: v
                            for k, v in data.items()
                            if k not in ("action", "tool", "result", "parameters")
                        }

                    # Redact full memory values in audit log records per privacy policy
                    audit_params = dict(parameters) if parameters else None
                    if audit_params and action_name in ("remember_fact", "save_note"):
                        for field in ("value", "content"):
                            if field in audit_params:
                                audit_params[field] = "[MEMORY_CONTENT_OMITTED]"
                    proposed_action = {"action": action_name, "parameters": audit_params}

                    eval_result = self.policy_engine.evaluate(action_name, parameters)

                    if eval_result.allowed:
                        policy_decision = "PERMITTED"
                        policy_reason = eval_result.reason
                        # Execute real safe tool (ignoring any hallucinated "result" field from LLM)
                        tool_func = getattr(self.tools, action_name, None)
                        if tool_func:
                            tool_result = tool_func(**parameters) if parameters else tool_func()
                            response_text = self.tools.format_tool_result(action_name, tool_result)
                            # Refresh system prompt immediately if profile facts changed
                            if action_name in ("remember_fact", "forget_fact"):
                                self.refresh_system_prompt()
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
