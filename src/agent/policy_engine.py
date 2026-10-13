"""
Policy Engine: Independently enforces permissions and boundaries.
Treats model outputs as untrusted. Never allows prompt injection or untrusted text
to grant shell execution, arbitrary file writes, raw SQL access, or admin capabilities.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, NamedTuple

from src.core.config import PROJECT_ROOT

HOST_REGEX = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-\._]{0,61}[a-zA-Z0-9])?$")
FORBIDDEN_CHAR_REGEX = re.compile(r"[;&|`$<>\n\r\t\"']")

# Authorized filesystem roots for file search
DEFAULT_AUTHORIZED_ROOTS = [
    PROJECT_ROOT.resolve(),
    (Path.home() / "Documents").resolve(),
    (Path.home() / "Desktop").resolve(),
    (Path.home() / "Downloads").resolve(),
]

# Sensitive directories never permitted for search
FORBIDDEN_SEARCH_DIRECTORIES = [
    r"c:\windows",
    r"c:\program files",
    r"c:\program files (x86)",
    r"\.git",
    r"\.venv",
    r"windows\system32",
]


class PolicyDecision(NamedTuple):
    allowed: bool
    reason: str
    requires_confirmation: bool = False
    risk_level: str = "safe_read"


class PolicyEngine:
    """Independent policy validation gate for tool authorization and argument checking."""

    PERMITTED_ACTIONS = {
        # System & Telemetry (Safe Read)
        "get_system_status",
        "get_battery_status",
        "get_resource_metrics",
        "get_network_adapter_status",
        "diagnostic_echo",
        "ping_host",
        # Memory & Notes (Safe Read / Safe Write)
        "remember_fact",
        "recall_facts",
        "forget_fact",
        "save_note",
        # Productivity & Tasks (Safe Write)
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
        # Applications (Controlled Launch)
        "launch_application",
        # Scoped File Search (Safe Read)
        "search_files",
        # Dictation / Text Insertion (Confirmation Required)
        "insert_text",
        # Connectivity & Hardware Queries (Safe Read)
        "get_wifi_status",
        "get_bluetooth_status",
        "check_camera_presence",
        "get_microphone_status",
        # Offline Messaging Queries (Safe Read)
        "get_telegram_status",
        "get_email_status",
    }

    CONFIRMATION_ACTIONS = {
        "insert_text",
        "delete_task",
    }

    FORBIDDEN_ACTIONS = {
        "execute_shell",
        "execute_powershell",
        "execute_cmd",
        "run_terminal_command",
        "powershell_script",
        "exec_calc",
        "delete_file",
        "write_system_file",
        "modify_registry",
        "access_internet",
        "execute_sql",
        "raw_sql",
        "drop_table",
        "delete_database",
    }

    # Strict application allowlist for launch_application
    ALLOWED_APPLICATIONS: dict[str, str] = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "explorer": "explorer.exe",
        "wordpad": "write.exe",
        "taskmgr": "taskmgr.exe",
    }

    def __init__(
        self,
        authorized_roots: list[Path] | None = None,
        forbidden_directories: list[str] | None = None,
    ):
        self.authorized_roots = (
            [r.resolve() for r in authorized_roots]
            if authorized_roots is not None
            else DEFAULT_AUTHORIZED_ROOTS
        )
        self.forbidden_directories = (
            [d.lower() for d in forbidden_directories]
            if forbidden_directories is not None
            else FORBIDDEN_SEARCH_DIRECTORIES
        )

    def evaluate(self, action_name: str, parameters: dict[str, Any] | None = None) -> PolicyDecision:
        """Evaluates whether an action proposed by the LLM is permitted and checks arguments."""
        if not action_name:
            return PolicyDecision(allowed=True, reason="Conversational response only (no tool requested).")

        lower_name = action_name.lower().strip()

        # Explicit denial of destructive / unrestricted shell or raw SQL actions
        if (
            action_name in self.FORBIDDEN_ACTIONS
            or "shell" in lower_name
            or "exec" in lower_name
            or "sql" in lower_name
            or "drop_" in lower_name
        ):
            return PolicyDecision(
                allowed=False,
                reason=f"Security Violation: '{action_name}' is forbidden by the local security policy.",
                risk_level="admin_denied",
            )

        # Allow only explicitly registered and permitted tool names
        if action_name not in self.PERMITTED_ACTIONS:
            return PolicyDecision(
                allowed=False,
                reason=f"Action '{action_name}' is not in the approved tool whitelist.",
                risk_level="unregistered",
            )

        params = parameters or {}

        # Argument validation for sensitive handlers
        if action_name == "launch_application":
            app = str(params.get("app_name") or params.get("app") or "").strip().lower()
            if not app:
                return PolicyDecision(allowed=False, reason="Missing required parameter 'app_name'.")
            if app not in self.ALLOWED_APPLICATIONS:
                allowed_list = ", ".join(sorted(self.ALLOWED_APPLICATIONS.keys()))
                return PolicyDecision(
                    allowed=False,
                    reason=f"Application '{app}' is not in the approved allowlist ({allowed_list}).",
                )

        elif action_name == "ping_host":
            host = str(params.get("host") or "").strip()
            if not host:
                return PolicyDecision(allowed=False, reason="Missing required parameter 'host'.")
            if FORBIDDEN_CHAR_REGEX.search(host) or not HOST_REGEX.match(host):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Security Violation: Host '{host}' contains invalid or prohibited shell characters.",
                )

        elif action_name == "search_files":
            root_dir_str = str(params.get("root_dir") or str(PROJECT_ROOT))
            try:
                target_path = Path(root_dir_str).resolve()
            except Exception as e:
                return PolicyDecision(allowed=False, reason=f"Invalid path: {e}")

            # Verify path traversal containment
            is_contained = any(
                target_path == auth_root or auth_root in target_path.parents
                for auth_root in self.authorized_roots
            )
            if not is_contained:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Filesystem Violation: Path '{target_path}' is outside authorized search roots.",
                )

            # Check forbidden system directories
            path_str_lower = str(target_path).lower()
            for forbidden_dir in self.forbidden_directories:
                if forbidden_dir in path_str_lower:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Filesystem Violation: Access to system directory '{forbidden_dir}' is prohibited.",
                    )

        # Check confirmation requirements
        needs_confirm = action_name in self.CONFIRMATION_ACTIONS
        risk = "confirmation" if needs_confirm else ("safe_write" if "create" in action_name or "update" in action_name or "save" in action_name or "remember" in action_name else "safe_read")

        return PolicyDecision(
            allowed=True,
            reason=f"Action '{action_name}' is authorized under safe tool registry.",
            requires_confirmation=needs_confirm,
            risk_level=risk,
        )
