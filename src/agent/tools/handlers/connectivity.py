"""
Connectivity Status Handler.
Queries local Wi-Fi and Bluetooth adapter states offline via native Windows utilities.
Zero external network calls, zero socket connections.
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any
import psutil

from src.agent.tools.models import ExecutionStatus, ToolResult

logger = logging.getLogger(__name__)


def get_wifi_status(**kwargs: Any) -> ToolResult:
    """
    Queries current Wi-Fi adapter state and connection parameters via netsh.
    Operates completely offline without sending any packets.
    """
    try:
        proc = subprocess.run(
            ["netsh.exe", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5.0,
            shell=False,
        )
        stdout = proc.stdout

        if "There is no wireless interface" in stdout or "no interface" in stdout.lower():
            return ToolResult.ok(
                {
                    "has_wifi": False,
                    "connected": False,
                    "ssid": None,
                    "signal_percent": 0,
                    "summary": "No wireless Wi-Fi adapter detected on this system.",
                }
            )

        # Parse interface fields
        state_match = re.search(r"^\s*State\s*:\s*(.+)$", stdout, re.MULTILINE)
        ssid_match = re.search(r"^\s*SSID\s*:\s*(.+)$", stdout, re.MULTILINE)
        signal_match = re.search(r"^\s*Signal\s*:\s*(\d+)%", stdout, re.MULTILINE)
        radio_match = re.search(r"^\s*Radio type\s*:\s*(.+)$", stdout, re.MULTILINE)

        state = state_match.group(1).strip() if state_match else "unknown"
        is_connected = state.lower() == "connected"
        ssid = ssid_match.group(1).strip() if ssid_match else None
        signal_pct = int(signal_match.group(1)) if signal_match else None
        radio = radio_match.group(1).strip() if radio_match else None

        if is_connected:
            summary = f"Wi-Fi is connected to '{ssid}' with {signal_pct}% signal strength ({radio})."
        else:
            summary = f"Wi-Fi adapter is present but currently {state}."

        return ToolResult.ok(
            {
                "has_wifi": True,
                "connected": is_connected,
                "state": state,
                "ssid": ssid,
                "signal_percent": signal_pct,
                "radio_type": radio,
                "summary": summary,
            }
        )
    except Exception as e:
        logger.error("Failed to query Wi-Fi status: %s", e)
        return ToolResult.fail(f"Failed to query Wi-Fi status: {e}")


def get_bluetooth_status(**kwargs: Any) -> ToolResult:
    """
    Queries local Windows Bluetooth subsystem status via Windows services.
    Operates completely offline without pairing or sending packets.
    """
    try:
        svc = psutil.win_service_get("bthserv")
        status = svc.status()
        is_active = status == "running"

        summary = (
            f"Bluetooth service is active and running."
            if is_active
            else f"Bluetooth service is currently {status}."
        )

        return ToolResult.ok(
            {
                "has_bluetooth": True,
                "service_status": status,
                "is_active": is_active,
                "summary": summary,
            }
        )
    except Exception as e:
        logger.warning("Could not query bthserv service: %s", e)
        return ToolResult.ok(
            {
                "has_bluetooth": False,
                "service_status": "unavailable",
                "is_active": False,
                "summary": "Bluetooth service is not available on this machine.",
            }
        )
