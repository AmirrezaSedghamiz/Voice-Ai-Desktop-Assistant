"""
Hardware Status Handler.
Checks camera presence and microphone hardware status strictly passively.
Zero camera recording, zero video capture, zero surveillance capabilities.
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any
import sounddevice as sd

from src.agent.tools.models import ExecutionStatus, ToolResult

logger = logging.getLogger(__name__)


def check_camera_presence(**kwargs: Any) -> ToolResult:
    """
    Checks whether video cameras or webcams are connected to the host system.
    STRICTLY PASSIVE: Performs device enumeration only; never opens camera stream or captures media.
    """
    try:
        proc = subprocess.run(
            ["pnputil.exe", "/enum-devices", "/class", "Camera"],
            capture_output=True,
            text=True,
            timeout=5.0,
            shell=False,
        )
        stdout = proc.stdout

        devices = []
        descriptions = re.findall(r"^\s*Device Description\s*:\s*(.+)$", stdout, re.MULTILINE)
        statuses = re.findall(r"^\s*Status\s*:\s*(.+)$", stdout, re.MULTILINE)

        for i, desc in enumerate(descriptions):
            st = statuses[i] if i < len(statuses) else "Unknown"
            devices.append({"name": desc.strip(), "status": st.strip()})

        has_camera = len(devices) > 0

        summary = (
            f"Detected {len(devices)} camera device(s): " + ", ".join([d["name"] for d in devices])
            if has_camera
            else "No camera devices detected."
        )

        return ToolResult.ok(
            {
                "camera_present": has_camera,
                "camera_count": len(devices),
                "devices": devices,
                "summary": summary,
            }
        )
    except Exception as e:
        logger.error("Failed to query camera presence: %s", e)
        return ToolResult.fail(f"Error checking camera hardware: {e}")


def get_microphone_status(**kwargs: Any) -> ToolResult:
    """
    Queries available audio input / recording hardware devices.
    Returns input device names and default input channel status.
    """
    try:
        all_devices = sd.query_devices()
        input_devices = [
            {"index": i, "name": d["name"], "channels": d["max_input_channels"]}
            for i, d in enumerate(all_devices)
            if d.get("max_input_channels", 0) > 0
        ]

        has_mic = len(input_devices) > 0
        default_in = sd.default.device[0] if hasattr(sd.default, "device") else None

        summary = (
            f"Detected {len(input_devices)} audio input device(s). Default device index: {default_in}."
            if has_mic
            else "No audio recording devices detected."
        )

        return ToolResult.ok(
            {
                "microphone_present": has_mic,
                "input_device_count": len(input_devices),
                "default_input_index": default_in,
                "devices": [d["name"] for d in input_devices[:5]],
                "summary": summary,
            }
        )
    except Exception as e:
        logger.error("Failed to query microphone status: %s", e)
        return ToolResult.fail(f"Error checking microphone hardware: {e}")
