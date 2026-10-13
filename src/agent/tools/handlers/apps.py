"""
Application Launcher Handler.
Enforces a strict allowlist of pre-approved local Windows utilities.
Launches exclusively via subprocess.Popen with shell=False.
Supports English and Persian friendly application aliases.
Zero arbitrary command execution.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from src.agent.tools.models import ExecutionStatus, ToolResult

logger = logging.getLogger(__name__)

# Strict application allowlist mapping canonical name to executable
ALLOWED_APP_MAP: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "taskmgr": "taskmgr.exe",
    "wordpad": "write.exe",
}

# English & Persian alias resolution mapping
APP_ALIASES: dict[str, str] = {
    # Persian aliases
    "یادداشت": "notepad",
    "نوت پد": "notepad",
    "نوت‌پد": "notepad",
    "ماشین حساب": "calculator",
    "ماشین‌حساب": "calculator",
    "نقاشی": "paint",
    "پینت": "paint",
    "اکسپلورر": "explorer",
    "فایل منیجر": "explorer",
    "فایل‌منیجر": "explorer",
    "پوشه": "explorer",
    "تسک منیجر": "taskmgr",
    "تسک‌منیجر": "taskmgr",
    # English aliases
    "note": "notepad",
    "notes": "notepad",
    "text editor": "notepad",
    "calc": "calculator",
    "mspaint": "paint",
    "file explorer": "explorer",
    "files": "explorer",
    "task manager": "taskmgr",
}


def resolve_app_name(name: str) -> str | None:
    """Resolves a user-provided English or Persian name to a canonical allowlisted application key."""
    if not name or not isinstance(name, str):
        return None
    cleaned = name.strip().lower()
    if cleaned in ALLOWED_APP_MAP:
        return cleaned
    if cleaned in APP_ALIASES:
        return APP_ALIASES[cleaned]
    # Check partial match in aliases
    for alias, canonical in APP_ALIASES.items():
        if alias in cleaned:
            return canonical
    return None


def launch_application(
    app_name: str,
    mock_for_test: bool = False,
    **kwargs: Any,
) -> ToolResult:
    """
    Launches an approved local desktop utility from the strict allowlist.
    Guarantees shell=False and zero arbitrary command injection.
    """
    canonical = resolve_app_name(app_name)
    if not canonical or canonical not in ALLOWED_APP_MAP:
        allowed_list = ", ".join(sorted(set(ALLOWED_APP_MAP.keys())))
        return ToolResult.fail(
            f"Application '{app_name}' is not in the approved allowlist ({allowed_list})."
        )

    exe = ALLOWED_APP_MAP[canonical]

    if mock_for_test:
        return ToolResult.ok(
            {
                "launched": canonical,
                "executable": exe,
                "pid": 99999,
                "message": f"Successfully launched {canonical} ({exe}) [MOCK].",
            }
        )

    try:
        # Strictly shell=False to prevent command injection
        proc = subprocess.Popen([exe], shell=False)
        logger.info("Launched application %s (exe: %s, pid: %s)", canonical, exe, proc.pid)
        return ToolResult.ok(
            {
                "launched": canonical,
                "executable": exe,
                "pid": proc.pid,
                "message": f"Successfully launched {canonical} ({exe}).",
            }
        )
    except Exception as e:
        logger.error("Failed to launch application %s: %s", canonical, e)
        return ToolResult.fail(f"Failed to launch {canonical}: {e}")
