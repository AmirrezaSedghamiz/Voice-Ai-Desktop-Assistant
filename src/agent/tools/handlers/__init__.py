"""
Tool Handlers Package.
Exports all safe, controlled tool implementations for Phase 4.
"""

from src.agent.tools.handlers.apps import launch_application, resolve_app_name
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

__all__ = [
    "TaskManager",
    "launch_application",
    "resolve_app_name",
    "ping_host",
    "get_battery_status",
    "get_system_status",
    "get_resource_metrics",
    "get_network_adapter_status",
    "diagnostic_echo",
    "insert_text",
    "search_files",
    "get_wifi_status",
    "get_bluetooth_status",
    "check_camera_presence",
    "get_microphone_status",
    "get_telegram_status",
    "get_email_status",
]
