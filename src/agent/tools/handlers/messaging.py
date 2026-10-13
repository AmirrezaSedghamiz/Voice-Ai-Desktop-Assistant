"""
Messaging Status Handler.
Provides offline reporting for local desktop email clients and Telegram.
Operates 100% offline without communicating with cloud APIs.
"""

from __future__ import annotations

import logging
from typing import Any
import psutil

from src.agent.tools.models import ExecutionStatus, ToolResult

logger = logging.getLogger(__name__)


def get_telegram_status(**kwargs: Any) -> ToolResult:
    """
    Checks whether Telegram Desktop application is running locally.
    Operates offline without connecting to Telegram servers.
    """
    is_running = False
    pid = None

    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info.get("name") or ""
                if name.lower() in ("telegram.exe", "telegram"):
                    is_running = True
                    pid = proc.info.get("pid")
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        summary = (
            f"Telegram Desktop is currently active and running (PID: {pid})."
            if is_running
            else "Telegram Desktop is not currently running."
        )

        return ToolResult.ok(
            {
                "is_running": is_running,
                "pid": pid,
                "offline_mode": True,
                "summary": summary,
            }
        )
    except Exception as e:
        logger.error("Failed to check Telegram process status: %s", e)
        return ToolResult.fail(f"Error checking Telegram status: {e}")


def get_email_status(**kwargs: Any) -> ToolResult:
    """
    Reports local email client status.
    Operates offline without polling external IMAP/SMTP/Exchange servers.
    """
    mail_clients = {"outlook.exe": "Microsoft Outlook", "thunderbird.exe": "Thunderbird", "hxoutlook.exe": "Windows Mail"}
    running_clients = []

    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in mail_clients:
                    running_clients.append(mail_clients[name])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        running_clients = list(set(running_clients))
        has_client = len(running_clients) > 0

        summary = (
            f"Local email client is active: {', '.join(running_clients)}. (Operating in offline mode)."
            if has_client
            else "No local email client is currently running. All operations remain offline."
        )

        return ToolResult.ok(
            {
                "client_running": has_client,
                "active_clients": running_clients,
                "offline_mode": True,
                "summary": summary,
            }
        )
    except Exception as e:
        logger.error("Failed to check email status: %s", e)
        return ToolResult.fail(f"Error checking email status: {e}")
