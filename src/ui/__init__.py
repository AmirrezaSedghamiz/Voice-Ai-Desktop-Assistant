"""
David Desktop UI Subsystem:
Qt-based native Windows interface, asynchronous thread workers,
offline wake-word integration, and system tray management.
"""

from src.ui.config import UiConfig
from src.ui.main_window import MainWindow

__all__ = ["UiConfig", "MainWindow"]
