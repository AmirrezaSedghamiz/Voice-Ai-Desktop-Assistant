"""
Dictation and Text Insertion Handler.
Types user-authorized text into the currently focused Windows application.
Preserves Unicode fidelity for English and Persian text.
Requires explicit user confirmation before any keystroke simulation.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import time
from typing import Any

from src.agent.tools.models import ExecutionStatus, ToolResult

logger = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _send_unicode_char(char: str) -> None:
    """Sends a single Unicode character to the active window via SendInput."""
    user32 = ctypes.windll.user32
    code_point = ord(char)

    # Key down
    ki_down = KEYBDINPUT(
        wVk=0,
        wScan=code_point,
        dwFlags=KEYEVENTF_UNICODE,
        time=0,
        dwExtraInfo=0,
    )
    inp_down = INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=ki_down))

    # Key up
    ki_up = KEYBDINPUT(
        wVk=0,
        wScan=code_point,
        dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
        time=0,
        dwExtraInfo=0,
    )
    inp_up = INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=ki_up))

    inputs = (INPUT * 2)(inp_down, inp_up)
    user32.SendInput(2, inputs, ctypes.sizeof(INPUT))


def insert_text(
    text: str,
    confirmed: bool = False,
    mock_for_test: bool = False,
    **kwargs: Any,
) -> ToolResult:
    """
    Simulates keyboard entry of text into the active foreground window.
    Requires explicit user confirmation before simulating keystrokes.
    """
    if not text or not isinstance(text, str):
        return ToolResult.fail("Text to insert cannot be empty.")

    cleaned_text = text.strip()
    if not cleaned_text:
        return ToolResult.fail("Text to insert cannot be blank.")

    # 1. Gate behind explicit confirmation
    if not confirmed:
        return ToolResult.needs_confirmation(
            action_name="insert_text",
            parameters={"text": cleaned_text, "confirmed": True},
            prompt=f"Please confirm typing the following text into the active window:\n'{cleaned_text}'",
        )

    # 2. Test mock execution
    if mock_for_test:
        return ToolResult.ok(
            {
                "text": cleaned_text,
                "length": len(cleaned_text),
                "status": "typed",
                "summary": f"Successfully simulated typing {len(cleaned_text)} characters [MOCK].",
            }
        )

    # 3. Native Windows typing execution
    try:
        # Small delay to ensure foreground focus stability
        time.sleep(0.1)
        for char in cleaned_text:
            _send_unicode_char(char)
            # Short sleep between characters for realistic entry
            time.sleep(0.005)

        logger.info("Successfully typed %d characters into focused window.", len(cleaned_text))
        return ToolResult.ok(
            {
                "text": cleaned_text,
                "length": len(cleaned_text),
                "status": "typed",
                "summary": f"Successfully typed {len(cleaned_text)} characters into active window.",
            }
        )
    except Exception as e:
        logger.error("Failed to type text via SendInput: %s", e)
        return ToolResult.fail(f"Failed to type text into active window: {e}")
