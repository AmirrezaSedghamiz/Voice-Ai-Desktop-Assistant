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
from src.agent.tools.handlers.apps import launch_application
from src.agent.tools.handlers.connectivity import get_bluetooth_status, get_wifi_status
from src.agent.tools.handlers.diagnostics import (
    diagnostic_echo,
    get_battery_status,
    get_network_adapter_status,
    get_resource_metrics,
    get_system_status,
    ping_host,
)
from src.agent.tools.handlers.dictation import insert_text
from src.agent.tools.handlers.file_search import search_files
from src.agent.tools.handlers.hardware import check_camera_presence, get_microphone_status
from src.agent.tools.handlers.messaging import get_email_status, get_telegram_status
from src.agent.tools.handlers.tasks import TaskManager
from src.agent.tools.models import ExecutionStatus, RiskLevel, ToolDefinition, ToolResult
from src.agent.tools.registry import ToolRegistry
from src.agent.tools.scheduler import ReminderScheduler
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

    # Exclude questions about identity (e.g., "اسم من چیه؟", "نام من چیست؟", "what is my name?")
    question_markers = ("چیه", "چیست", "چی بود", "چی هست", "کیه", "کیست", "یادته", "میدونی", "می‌دونی", "؟", "?")
    if any(q in text for q in question_markers):
        if any(w in text.lower() for w in ("اسم", "نام", "name", "who am i", "what")):
            return None

    # Persian patterns: "اسم من ... است/هست", "نام من ... است/هست", "اسمم ... است/هست"
    fa_match = re.search(
        r"(?:اسم من|نام من|اسمم)\s+([A-Za-z\u0600-\u06FF\s]+?)(?:\s+(?:است|هست|هستم|می‌باشد|میباشد)|[\.!\?،,]|$)",
        text,
        re.IGNORECASE,
    )
    if fa_match:
        name = fa_match.group(1).strip()
        if name and name not in ("چی", "چیه", "چیست", "کی", "کیه", "چیزی") and len(name) < 50:
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
            if cleaned and not cleaned.lower().startswith(("not ", "no ", "a user", "trying", "what", "who")):
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
- CRITICAL: You cannot execute real actions, inspect hardware, search files, manage tasks or modify memories by replying in plain text. Whenever the user requests one of these operations, you MUST respond ONLY with a raw JSON object in one of these exact formats and NO other text (NEVER include a "result" field):
- Battery percentage & power: {"action": "get_battery_status"}
- Overall system health/CPUs: {"action": "get_system_status"}
- CPU/RAM load metrics: {"action": "get_resource_metrics"}
- Wi-Fi adapter connection & SSID: {"action": "get_wifi_status"}
- Bluetooth status: {"action": "get_bluetooth_status"}
- Camera presence check: {"action": "check_camera_presence"}
- Microphone audio input check: {"action": "get_microphone_status"}
- Telegram Desktop process check: {"action": "get_telegram_status"}
- Offline email client check: {"action": "get_email_status"}
- Ping local router/host: {"action": "ping_host", "parameters": {"host": "<hostname_or_ip>"}}
- Launch approved utility (Notepad, Calculator, Paint, Explorer, Task Manager): {"action": "launch_application", "parameters": {"app_name": "<name>"}}
- Create task: {"action": "create_task", "parameters": {"title": "<task_title>", "due_date": "<optional_due_date>"}}
- List tasks: {"action": "list_tasks"}
- Complete task: {"action": "complete_task", "parameters": {"task_id": <id>}}
- Delete task: {"action": "delete_task", "parameters": {"task_id": <id>}}
- Create reminder: {"action": "create_reminder", "parameters": {"message": "<reminder_text>", "duration_minutes": <minutes>}}
- Break reminder (e.g. 45 min): {"action": "schedule_break_reminder", "parameters": {"minutes": 45}}
- List reminders: {"action": "list_reminders"}
- Cancel reminder: {"action": "cancel_reminder", "parameters": {"reminder_id": <id>}}
- Search files: {"action": "search_files", "parameters": {"pattern": "<filename_or_keyword>"}}
- Type text into focused app: {"action": "insert_text", "parameters": {"text": "<text_to_type>"}}
- Remember fact/preference: {"action": "remember_fact", "parameters": {"key": "<short_snake_case_key>", "value": "<fact_value>", "category": "profile"}}
- Search memory/notes: {"action": "recall_facts", "parameters": {"query": "<search_keywords>"}}
- Forget saved fact: {"action": "forget_fact", "parameters": {"key": "<fact_key>"}}
- Save note: {"action": "save_note", "parameters": {"title": "<note_title>", "content": "<note_content>"}}
"""

# Alias preserved for backwards compatibility
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT


class SafeToolRegistry:
    """Safe, schema-validated tool implementations with bounded scopes."""

    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        task_manager: TaskManager | None = None,
        policy_engine: PolicyEngine | None = None,
    ):
        self.memory_store = memory_store
        db_path = getattr(memory_store, "db_path", None)
        self.task_manager = task_manager or TaskManager(db_path=db_path)
        self.policy_engine = policy_engine
        self.registry = ToolRegistry()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        defs = [
            ToolDefinition(name="get_system_status", description="Get CPU count and RAM summary", risk_level=RiskLevel.SAFE_READ, handler=self.get_system_status),
            ToolDefinition(name="get_battery_status", description="Get battery level and charging state", risk_level=RiskLevel.SAFE_READ, handler=self.get_battery_status),
            ToolDefinition(name="get_resource_metrics", description="Get CPU, RAM and disk usage", risk_level=RiskLevel.SAFE_READ, handler=self.get_resource_metrics),
            ToolDefinition(name="get_network_adapter_status", description="Get physical network adapters", risk_level=RiskLevel.SAFE_READ, handler=self.get_network_adapter_status),
            ToolDefinition(name="ping_host", description="Ping local hostname or IP", risk_level=RiskLevel.SAFE_READ, handler=self.ping_host),
            ToolDefinition(name="remember_fact", description="Save user fact to persistent memory", risk_level=RiskLevel.SAFE_WRITE, handler=self.remember_fact),
            ToolDefinition(name="recall_facts", description="Search memory and notes via FTS5", risk_level=RiskLevel.SAFE_READ, handler=self.recall_facts),
            ToolDefinition(name="forget_fact", description="Delete saved memory fact", risk_level=RiskLevel.SAFE_WRITE, handler=self.forget_fact),
            ToolDefinition(name="save_note", description="Save durable note", risk_level=RiskLevel.SAFE_WRITE, handler=self.save_note),
            ToolDefinition(name="create_task", description="Create new task", risk_level=RiskLevel.SAFE_WRITE, handler=self.create_task),
            ToolDefinition(name="list_tasks", description="List tasks", risk_level=RiskLevel.SAFE_READ, handler=self.list_tasks),
            ToolDefinition(name="get_task", description="Get task by ID", risk_level=RiskLevel.SAFE_READ, handler=self.get_task),
            ToolDefinition(name="update_task_status", description="Update task status", risk_level=RiskLevel.SAFE_WRITE, handler=self.update_task_status),
            ToolDefinition(name="complete_task", description="Complete task by ID", risk_level=RiskLevel.SAFE_WRITE, handler=self.complete_task),
            ToolDefinition(name="delete_task", description="Delete task by ID", risk_level=RiskLevel.CONFIRMATION_REQUIRED, requires_confirmation=True, handler=self.delete_task),
            ToolDefinition(name="create_reminder", description="Create scheduled reminder", risk_level=RiskLevel.SAFE_WRITE, handler=self.create_reminder),
            ToolDefinition(name="list_reminders", description="List upcoming reminders", risk_level=RiskLevel.SAFE_READ, handler=self.list_reminders),
            ToolDefinition(name="cancel_reminder", description="Cancel pending reminder", risk_level=RiskLevel.SAFE_WRITE, handler=self.cancel_reminder),
            ToolDefinition(name="reschedule_reminder", description="Reschedule reminder", risk_level=RiskLevel.SAFE_WRITE, handler=self.reschedule_reminder),
            ToolDefinition(name="schedule_break_reminder", description="Schedule a break reminder", risk_level=RiskLevel.SAFE_WRITE, handler=self.schedule_break_reminder),
            ToolDefinition(name="launch_application", description="Launch approved utility", risk_level=RiskLevel.SAFE_WRITE, handler=self.launch_application),
            ToolDefinition(name="search_files", description="Search files in authorized roots", risk_level=RiskLevel.SAFE_READ, handler=self.search_files),
            ToolDefinition(name="insert_text", description="Type text into focused window", risk_level=RiskLevel.CONFIRMATION_REQUIRED, requires_confirmation=True, handler=self.insert_text),
            ToolDefinition(name="get_wifi_status", description="Query Wi-Fi status", risk_level=RiskLevel.SAFE_READ, handler=self.get_wifi_status),
            ToolDefinition(name="get_bluetooth_status", description="Query Bluetooth status", risk_level=RiskLevel.SAFE_READ, handler=self.get_bluetooth_status),
            ToolDefinition(name="check_camera_presence", description="Check camera presence", risk_level=RiskLevel.SAFE_READ, handler=self.check_camera_presence),
            ToolDefinition(name="get_microphone_status", description="Get microphone hardware status", risk_level=RiskLevel.SAFE_READ, handler=self.get_microphone_status),
            ToolDefinition(name="get_telegram_status", description="Check Telegram running status", risk_level=RiskLevel.SAFE_READ, handler=self.get_telegram_status),
            ToolDefinition(name="get_email_status", description="Check offline email client status", risk_level=RiskLevel.SAFE_READ, handler=self.get_email_status),
            ToolDefinition(name="diagnostic_echo", description="Echo diagnostic message", risk_level=RiskLevel.SAFE_READ, handler=self.diagnostic_echo),
        ]
        for d in defs:
            try:
                self.registry.register(d)
            except Exception as e:
                logger.debug("Tool definition registration: %s", e)

    @staticmethod
    def get_system_status(**kwargs: Any) -> dict[str, Any]:
        """Returns non-sensitive host system summary."""
        res = get_system_status(**kwargs)
        return res.result if isinstance(res, ToolResult) else res

    @staticmethod
    def get_battery_status(**kwargs: Any) -> dict[str, Any]:
        """Returns laptop battery percentage and charging state."""
        res = get_battery_status(**kwargs)
        return res.result if isinstance(res, ToolResult) else res

    @staticmethod
    def get_resource_metrics(**kwargs: Any) -> dict[str, Any]:
        """Returns current CPU and RAM load."""
        res = get_resource_metrics(**kwargs)
        return res.result if isinstance(res, ToolResult) else res

    @staticmethod
    def get_network_adapter_status(**kwargs: Any) -> ToolResult:
        """Returns status of local physical network adapters."""
        return get_network_adapter_status(**kwargs)

    @staticmethod
    def ping_host(host: str = "", count: int = 2, **kwargs: Any) -> ToolResult:
        """Pings an approved host without shell."""
        return ping_host(host=host, count=count, **kwargs)

    @staticmethod
    def launch_application(app_name: str = "", **kwargs: Any) -> ToolResult:
        """Launches an allowlisted utility."""
        return launch_application(app_name=app_name, **kwargs)

    def search_files(
        self,
        pattern: str = "",
        root_dir: str | None = None,
        extension: str | None = None,
        max_results: int = 20,
        **kwargs: Any,
    ) -> ToolResult:
        """Scoped file search within authorized roots."""
        return search_files(
            pattern=pattern,
            root_dir=root_dir,
            extension=extension,
            max_results=max_results,
            policy_engine=self.policy_engine,
            **kwargs,
        )

    @staticmethod
    def insert_text(text: str = "", confirmed: bool = False, **kwargs: Any) -> ToolResult:
        """Types text into active window."""
        return insert_text(text=text, confirmed=confirmed, **kwargs)

    @staticmethod
    def get_wifi_status(**kwargs: Any) -> ToolResult:
        """Queries Wi-Fi status."""
        return get_wifi_status(**kwargs)

    @staticmethod
    def get_bluetooth_status(**kwargs: Any) -> ToolResult:
        """Queries Bluetooth status."""
        return get_bluetooth_status(**kwargs)

    @staticmethod
    def check_camera_presence(**kwargs: Any) -> ToolResult:
        """Checks camera hardware presence passively."""
        return check_camera_presence(**kwargs)

    @staticmethod
    def get_microphone_status(**kwargs: Any) -> ToolResult:
        """Queries microphone hardware status."""
        return get_microphone_status(**kwargs)

    @staticmethod
    def get_telegram_status(**kwargs: Any) -> ToolResult:
        """Checks if Telegram desktop is running."""
        return get_telegram_status(**kwargs)

    @staticmethod
    def get_email_status(**kwargs: Any) -> ToolResult:
        """Checks offline email client status."""
        return get_email_status(**kwargs)

    @staticmethod
    def diagnostic_echo(message: str = "", **kwargs: Any) -> ToolResult:
        """Echoes a message for diagnostics."""
        return diagnostic_echo(message=message, **kwargs)

    def create_task(
        self,
        title: str = "",
        description: str = "",
        due_date: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        return self.task_manager.create_task(title=title, description=description, due_date=due_date, **kwargs)

    def list_tasks(self, status: str | None = None, **kwargs: Any) -> ToolResult:
        return self.task_manager.list_tasks(status=status, **kwargs)

    def get_task(self, task_id: int | str = 0, **kwargs: Any) -> ToolResult:
        return self.task_manager.get_task(task_id=task_id, **kwargs)

    def update_task_status(self, task_id: int | str = 0, status: str = "", **kwargs: Any) -> ToolResult:
        return self.task_manager.update_task_status(task_id=task_id, status=status, **kwargs)

    def complete_task(self, task_id: int | str = 0, **kwargs: Any) -> ToolResult:
        return self.task_manager.complete_task(task_id=task_id, **kwargs)

    def delete_task(self, task_id: int | str = 0, confirmed: bool = False, **kwargs: Any) -> ToolResult:
        return self.task_manager.delete_task(task_id=task_id, confirmed=confirmed, **kwargs)

    def create_reminder(
        self,
        message: str = "",
        due_time: str | None = None,
        duration_minutes: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        return self.task_manager.create_reminder(message=message, due_time=due_time, duration_minutes=duration_minutes, **kwargs)

    def list_reminders(self, include_completed: bool = False, **kwargs: Any) -> ToolResult:
        return self.task_manager.list_reminders(include_completed=include_completed, **kwargs)

    def cancel_reminder(self, reminder_id: int | str = 0, **kwargs: Any) -> ToolResult:
        return self.task_manager.cancel_reminder(reminder_id=reminder_id, **kwargs)

    def reschedule_reminder(self, reminder_id: int | str = 0, new_due_time: str = "", **kwargs: Any) -> ToolResult:
        return self.task_manager.reschedule_reminder(reminder_id=reminder_id, new_due_time=new_due_time, **kwargs)

    def schedule_break_reminder(self, minutes: int | str = 45, **kwargs: Any) -> ToolResult:
        return self.task_manager.schedule_break_reminder(minutes=minutes, **kwargs)

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
    def format_tool_result(action_name: str, result: dict[str, Any] | ToolResult) -> str:
        """Converts raw tool output into a natural spoken sentence."""
        if isinstance(result, ToolResult):
            if result.status == ExecutionStatus.AWAITING_CONFIRMATION:
                return result.result.get("confirmation_prompt") or f"Please confirm action '{action_name}'."
            if not result.success:
                return f"Could not perform '{action_name}': {result.error}"
            res = result.result
        elif isinstance(result, dict):
            if result.get("status") == "awaiting_confirmation":
                return result.get("confirmation_prompt") or f"Please confirm action '{action_name}'."
            res = result
        else:
            return str(result)

        if action_name == "get_battery_status":
            if not res.get("battery_present", True):
                return "No battery was detected. Your system is running on direct AC power."
            pct = res.get("percent", 0)
            plugged = res.get("power_plugged", False)
            state = "plugged into power" if plugged else "running on battery power"
            secs = res.get("seconds_left")
            if not plugged and isinstance(secs, (int, float)) and secs > 0:
                mins = int(secs // 60)
                return f"Your laptop battery is at {pct}% and {state}, with approximately {mins} minutes remaining."
            return f"Your laptop battery is at {pct}% and {state}."

        if action_name == "get_system_status":
            return (
                f"Your system status is {res.get('status', 'healthy')}. "
                f"It has {res.get('cpu_count')} logical CPU cores, and memory usage is at "
                f"{res.get('ram_used_gb')} gigabytes out of {res.get('ram_total_gb')} gigabytes "
                f"({res.get('ram_percent')}%)."
            )

        if action_name == "get_resource_metrics":
            return (
                f"Current CPU load is {res.get('cpu_percent')}%, and RAM usage is at "
                f"{res.get('virtual_memory_percent')}%."
            )

        if action_name == "remember_fact":
            status = res.get("status")
            if status in ("created", "updated", "unchanged"):
                readable_key = str(res.get("key", "")).replace("_", " ")
                return f"I have saved that in my long-term memory: {readable_key} is {res.get('value')}."
            return str(res.get("message", "Could not save that fact."))

        if action_name == "recall_facts":
            status = res.get("status")
            hits = res.get("results", [])
            if status == "ok" and hits:
                items = [
                    f"{h['key_or_title'].replace('_', ' ')}: {h['content']}"
                    for h in hits[:5]
                ]
                return "Here is what I found in your saved memory: " + "; ".join(items) + "."
            if status == "empty":
                return f"I checked my saved memory for {res.get('query', 'that topic')}, but found no matching records."
            return str(res.get("message", "Could not search memory."))

        if action_name == "forget_fact":
            status = res.get("status")
            if status == "deleted":
                readable_key = str(res.get("key", "")).replace("_", " ")
                return f"I have removed {readable_key} from my long-term memory."
            return str(res.get("message", "Could not remove that fact."))

        if action_name == "save_note":
            if res.get("status") == "saved":
                return f"I have saved your note titled {res.get('title')}."
            return str(res.get("message", "Could not save that note."))

        if action_name == "create_task":
            return res.get("message") or f"I have created task #{res.get('task_id')}: '{res.get('title')}'."

        if action_name == "list_tasks":
            tasks = res.get("tasks", [])
            if not tasks:
                return "You have no tasks saved."
            items = [f"#{t['id']} {t['title']} ({t['status']})" for t in tasks[:5]]
            return f"You have {len(tasks)} tasks: " + "; ".join(items) + "."

        if action_name == "get_task":
            return f"Task #{res.get('id')} is '{res.get('title')}', status is {res.get('status')}."

        if action_name in ("update_task_status", "complete_task", "delete_task"):
            return str(res.get("message", f"Task updated."))

        if action_name in ("create_reminder", "schedule_break_reminder"):
            return str(res.get("message_summary") or res.get("message", "Reminder scheduled."))

        if action_name == "list_reminders":
            rems = res.get("reminders", [])
            if not rems:
                return "You have no pending reminders."
            items = [f"#{r['id']} {r['message']}" for r in rems[:5]]
            return f"You have {len(rems)} reminders: " + "; ".join(items) + "."

        if action_name in ("cancel_reminder", "reschedule_reminder"):
            return str(res.get("message", "Reminder updated."))

        if action_name == "launch_application":
            return str(res.get("message", f"Launched application {res.get('launched')}."))

        if action_name == "search_files":
            count = res.get("count", 0)
            hits = res.get("results", [])
            if count == 0:
                return str(res.get("summary") or "No matching files found.")
            file_names = ", ".join([h["name"] for h in hits[:5]])
            return f"Found {count} matching files: {file_names}."

        if action_name == "insert_text":
            return str(res.get("summary", "Text inserted into active application."))

        # Telemetry, Diagnostics & Hardware tools with summary
        if "summary" in res:
            return str(res["summary"])

        # Fallback for any other tool
        parts = [f"{k.replace('_', ' ')} is {v}" for k, v in res.items()]
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
        task_manager: TaskManager | None = None,
    ):
        self.llm_client = llm_client
        self.policy_engine = policy_engine
        self.audit_logger = audit_logger
        self.governor = governor
        self.memory_store = memory_store
        self.tools = SafeToolRegistry(
            memory_store=memory_store,
            task_manager=task_manager,
            policy_engine=policy_engine,
        )
        self.pending_confirmation: dict[str, Any] | None = None
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

        # Handle pending confirmation flow if awaiting user approval
        if self.pending_confirmation:
            cleaned_input = user_text.strip().lower()
            CONFIRM_WORDS = {"yes", "yeah", "yep", "sure", "confirm", "proceed", "do it", "ok", "okay", "بله", "آره", "تایید", "انجام بده", "حله", "باشه"}
            CANCEL_WORDS = {"no", "nope", "cancel", "stop", "don't", "dont", "abort", "نه", "خیر", "لغو", "کنسل", "نکن"}

            tokens = set(re.findall(r"[\w\u0600-\u06FF]+", cleaned_input))
            is_confirm = bool(tokens & CONFIRM_WORDS)
            is_cancel = bool(tokens & CANCEL_WORDS)

            if is_confirm:
                pending = self.pending_confirmation
                self.pending_confirmation = None
                action_name = pending["action"]
                params = dict(pending.get("parameters") or {})
                params["confirmed"] = True

                tool_func = getattr(self.tools, action_name, None)
                if tool_func:
                    tool_result = tool_func(**params)
                    response_text = self.tools.format_tool_result(action_name, tool_result)
                else:
                    response_text = f"Action '{action_name}' could not be executed."

                self.conversation_history.append({"role": "user", "content": user_text})
                self.conversation_history.append({"role": "assistant", "content": response_text})

                mock_metrics = InferenceMetrics()
                mock_metrics.total_generation_time = 0.01
                self.audit_logger.log_event(
                    event_type="chat_turn_confirmation",
                    user_input=user_text,
                    proposed_action={"action": action_name, "parameters": params},
                    policy_decision="PERMITTED",
                    policy_reason="User confirmed pending action",
                    model_output=response_text,
                    metrics={"tps": 0.0, "total_time_s": 0.01, "prompt_tokens": 0, "completion_tokens": 0},
                )
                return response_text, mock_metrics
            elif is_cancel:
                self.pending_confirmation = None
                response_text = "Action cancelled. The operation was not executed."
                self.conversation_history.append({"role": "user", "content": user_text})
                self.conversation_history.append({"role": "assistant", "content": response_text})

                mock_metrics = InferenceMetrics()
                mock_metrics.total_generation_time = 0.01
                self.audit_logger.log_event(
                    event_type="chat_turn_cancellation",
                    user_input=user_text,
                    proposed_action=None,
                    policy_decision="USER_CANCELLED",
                    policy_reason="User cancelled pending action",
                    model_output=response_text,
                    metrics={"tps": 0.0, "total_time_s": 0.01, "prompt_tokens": 0, "completion_tokens": 0},
                )
                return response_text, mock_metrics
            else:
                self.pending_confirmation = None

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
                if isinstance(data, dict):
                    action_name = str(data.get("action") or data.get("tool") or "").strip()
                    if not action_name:
                        before_brace = response_text[: response_text.find("{")].strip()
                        ALL_KNOWN_ACTIONS = (
                            "recall_facts",
                            "remember_fact",
                            "forget_fact",
                            "save_note",
                            "get_battery_status",
                            "get_system_status",
                            "get_resource_metrics",
                            "get_network_adapter_status",
                            "ping_host",
                            "launch_application",
                            "create_task",
                            "list_tasks",
                            "get_task",
                            "update_task_status",
                            "complete_task",
                            "delete_task",
                            "create_reminder",
                            "list_reminders",
                            "cancel_reminder",
                            "reschedule_reminder",
                            "schedule_break_reminder",
                            "search_files",
                            "insert_text",
                            "get_wifi_status",
                            "get_bluetooth_status",
                            "check_camera_presence",
                            "get_microphone_status",
                            "get_telegram_status",
                            "get_email_status",
                            "diagnostic_echo",
                        )
                        for known_action in ALL_KNOWN_ACTIONS:
                            if known_action in before_brace:
                                action_name = known_action
                                break

                    if action_name:
                        if isinstance(data.get("parameters"), dict):
                            parameters = dict(data["parameters"])
                        else:
                            # Support flattened arguments from compact models (excluding meta keys)
                            parameters = {
                                k: v
                                for k, v in data.items()
                                if k not in ("action", "tool", "result", "parameters")
                            }

                        # Redact full memory/dictation values in audit log records per privacy policy
                        audit_params = dict(parameters) if parameters else None
                        if audit_params:
                            for field in ("value", "content"):
                                if field in audit_params:
                                    audit_params[field] = "[MEMORY_CONTENT_OMITTED]"
                            if "text" in audit_params:
                                audit_params["text"] = "[TEXT_CONTENT_OMITTED]"
                        proposed_action = {"action": action_name, "parameters": audit_params}

                        eval_result = self.policy_engine.evaluate(action_name, parameters)

                        if eval_result.allowed:
                            policy_decision = "PERMITTED"
                            policy_reason = eval_result.reason
                            # Execute real safe tool (ignoring any hallucinated "result" field from LLM)
                            tool_func = getattr(self.tools, action_name, None)
                            if tool_func:
                                tool_result = tool_func(**parameters) if parameters else tool_func()
                                if (
                                    (isinstance(tool_result, ToolResult) and tool_result.status == ExecutionStatus.AWAITING_CONFIRMATION)
                                    or (isinstance(tool_result, dict) and tool_result.get("status") == "awaiting_confirmation")
                                ):
                                    self.pending_confirmation = {"action": action_name, "parameters": parameters}
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
