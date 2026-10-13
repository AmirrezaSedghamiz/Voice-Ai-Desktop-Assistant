"""
System Tray Manager for David Assistant:
Provides background minimization, status notifications, and quick control actions.
"""

import logging
from typing import Callable
from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

logger = logging.getLogger("assistant.ui.tray")


class SystemTrayManager(QObject):
    """Manages the Windows system tray icon, notification popups, and quick menu."""

    def __init__(
        self,
        icon: QIcon,
        on_show_window: Callable[[], None],
        on_toggle_wake_word: Callable[[], bool],  # returns is_paused
        on_open_settings: Callable[[], None],
        on_exit_app: Callable[[], None],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.on_show_window = on_show_window
        self.on_toggle_wake_word = on_toggle_wake_word
        self.on_open_settings = on_open_settings
        self.on_exit_app = on_exit_app

        self.tray_icon = QSystemTrayIcon(icon, parent)
        self.tray_icon.setToolTip("David - Local AI Assistant")

        # Context Menu
        self.menu = QMenu()

        self.open_action = QAction("Open David", self.menu)
        self.open_action.triggered.connect(self.on_show_window)
        self.menu.addAction(self.open_action)

        self.menu.addSeparator()

        self.wake_toggle_action = QAction("Pause Wake-Word", self.menu)
        self.wake_toggle_action.triggered.connect(self._handle_wake_toggle)
        self.menu.addAction(self.wake_toggle_action)

        self.settings_action = QAction("Settings...", self.menu)
        self.settings_action.triggered.connect(self.on_open_settings)
        self.menu.addAction(self.settings_action)

        self.menu.addSeparator()

        self.exit_action = QAction("Exit David", self.menu)
        self.exit_action.triggered.connect(self.on_exit_app)
        self.menu.addAction(self.exit_action)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._on_tray_activated)

    def show(self) -> None:
        self.tray_icon.show()

    def hide(self) -> None:
        self.tray_icon.hide()

    def update_wake_status(self, is_paused: bool) -> None:
        if is_paused:
            self.wake_toggle_action.setText("Resume Wake-Word")
            self.tray_icon.setToolTip("David - Local AI Assistant (Wake Paused)")
        else:
            self.wake_toggle_action.setText("Pause Wake-Word")
            self.tray_icon.setToolTip("David - Local AI Assistant (Listening)")

    def _handle_wake_toggle(self) -> None:
        is_paused = self.on_toggle_wake_word()
        self.update_wake_status(is_paused)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.on_show_window()

    def show_message(self, title: str, message: str, msecs: int = 3000) -> None:
        """Displays a native Windows balloon notification."""
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, msecs)
