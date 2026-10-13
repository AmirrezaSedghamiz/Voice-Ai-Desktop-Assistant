"""
Main Application Window for David Desktop Assistant:
Coordinates the conversational UI, asynchronous Qt background workers,
voice push-to-talk, wake-word activation, and Windows system tray minimization.
"""

import logging
from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.adapter.llm_client import InferenceMetrics
from src.agent.orchestrator import SafeAgentOrchestrator
from src.audio.voice_session import VoiceSessionManager
from src.audio.wake_word import WakeWordConfig, WakeWordDetector
from src.ui.config import UiConfig
from src.ui.icon import get_app_icon
from src.ui.settings_dialog import SettingsDialog
from src.ui.styles import MAIN_STYLESHEET
from src.ui.tray import SystemTrayManager
from src.ui.widgets import ChatBubbleWidget, EmptyStateWidget, StatusBadgeWidget
from src.ui.workers import InferenceWorker, VoiceTurnWorker, WakeWordWorker

logger = logging.getLogger("assistant.ui.main_window")


class AutoGrowingTextEdit(QTextEdit):
    """Multiline text input that sends on Enter and inserts newlines on Shift+Enter."""

    return_pressed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("messageInput")
        self.setPlaceholderText("Type a message or request in English or Persian (Shift+Enter for newline)...")
        self.setFixedHeight(46)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.return_pressed.emit()
                event.accept()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    """Main desktop application window for David assistant."""

    def __init__(
        self,
        orchestrator: SafeAgentOrchestrator,
        voice_session: VoiceSessionManager,
        ui_config: UiConfig | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.voice_session = voice_session
        self.ui_config = ui_config or UiConfig.load()

        self.app_icon = get_app_icon()
        self.setWindowIcon(self.app_icon)
        self.setWindowTitle("David - Local AI Assistant")
        self.resize(760, 800)
        self.setMinimumSize(540, 600)
        self.setStyleSheet(MAIN_STYLESHEET)

        # Worker management
        self.inference_worker: InferenceWorker | None = None
        self.voice_worker: VoiceTurnWorker | None = None
        self.wake_detector: WakeWordDetector | None = None
        self.wake_worker: WakeWordWorker | None = None
        self.is_wake_paused: bool = False
        self._first_minimize_notification: bool = True

        self._init_ui()
        self._init_tray()
        self._init_wake_word()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Bar
        header = QFrame()
        header.setObjectName("headerWidget")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(12)

        # Title and Subtitle
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel(self.ui_config.assistant_name)
        title_label.setObjectName("appTitle")
        subtitle_label = QLabel("Fully Local & Offline Windows AI Assistant")
        subtitle_label.setObjectName("appSubtitle")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Status Badge
        self.status_badge = StatusBadgeWidget()
        header_layout.addWidget(self.status_badge)

        # Settings Button
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(self.settings_btn)

        main_layout.addWidget(header)

        # 2. Conversation History Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("conversationScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.conversation_widget = QWidget()
        self.conversation_widget.setObjectName("conversationContainer")
        self.conversation_layout = QVBoxLayout(self.conversation_widget)
        self.conversation_layout.setContentsMargins(20, 20, 20, 20)
        self.conversation_layout.setSpacing(14)
        self.conversation_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Empty State
        self.empty_state = EmptyStateWidget()
        self.empty_state.suggestion_clicked.connect(self._handle_suggestion_click)
        self.conversation_layout.addWidget(self.empty_state)

        self.scroll_area.setWidget(self.conversation_widget)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # 3. Input & Controls Footer
        input_container = QFrame()
        input_container.setObjectName("inputContainer")
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(16, 12, 16, 14)
        input_layout.setSpacing(10)

        # Text input row
        self.text_input = AutoGrowingTextEdit()
        self.text_input.return_pressed.connect(self.send_text_message)
        input_layout.addWidget(self.text_input)

        # Buttons row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        # Push-to-Talk / Mic Button
        self.mic_btn = QPushButton("🎤 Speak")
        self.mic_btn.setObjectName("micButton")
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setFixedWidth(110)
        self.mic_btn.clicked.connect(self.toggle_voice_turn)
        controls_layout.addWidget(self.mic_btn)

        # Stop / Cancel Button
        self.stop_btn = QPushButton("■ Cancel")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setFixedWidth(90)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.cancel_active_operation)
        controls_layout.addWidget(self.stop_btn)

        controls_layout.addStretch()

        # Send Button
        self.send_btn = QPushButton("Send ↵")
        self.send_btn.setObjectName("sendButton")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setFixedWidth(100)
        self.send_btn.clicked.connect(self.send_text_message)
        controls_layout.addWidget(self.send_btn)

        input_layout.addLayout(controls_layout)
        main_layout.addWidget(input_container)

    def _init_tray(self) -> None:
        self.tray = SystemTrayManager(
            icon=self.app_icon,
            on_show_window=self.restore_window,
            on_toggle_wake_word=self.toggle_wake_word_listening,
            on_open_settings=self.open_settings,
            on_exit_app=self.exit_application,
            parent=self,
        )
        self.tray.show()

    def _init_wake_word(self) -> None:
        """Initializes the background wake-word worker if enabled."""
        if not self.ui_config.wake_word_enabled:
            self.status_badge.set_state("idle", "Ready")
            return

        try:
            from src.ui.app import resolve_model_file
            ww_cfg = WakeWordConfig(
                phrase=self.ui_config.wake_phrase,
                model_dir=resolve_model_file("wake_word/vosk-model-small-en-us-0.15"),
                energy_threshold=self.ui_config.wake_energy_threshold,
                input_device_index=self.ui_config.input_device_index,
                enabled=self.ui_config.wake_word_enabled,
            )
            self.wake_detector = WakeWordDetector(ww_cfg)
            self.wake_worker = WakeWordWorker(self.wake_detector, parent=self)
            self.wake_worker.wake_word_detected.connect(self._on_wake_word_triggered)
            self.wake_worker.error.connect(self._on_wake_word_error)
            self.wake_worker.start()
            self.status_badge.set_state("wake_listening")
            logger.info("Wake-word worker started successfully.")
        except Exception as e:
            logger.warning("Could not initialize wake-word detector: %s", e)
            self.status_badge.set_state("idle", "Ready (Wake Offline)")

    def _handle_suggestion_click(self, suggestion_text: str) -> None:
        self.text_input.setPlainText(suggestion_text)
        self.send_text_message()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def add_message_bubble(self, sender: str, text: str, tool_info: str | None = None) -> None:
        """Appends a new message bubble to the conversation area."""
        if self.empty_state.isVisible():
            self.empty_state.hide()

        bubble = ChatBubbleWidget(sender=sender, text=text, tool_info=tool_info)
        self.conversation_layout.addWidget(bubble)
        self._scroll_to_bottom()

    def send_text_message(self) -> None:
        """Sends the user input text to the orchestrator on a background worker thread."""
        user_text = self.text_input.toPlainText().strip()
        if not user_text:
            return

        # Clear text input
        self.text_input.clear()
        self.add_message_bubble(sender="user", text=user_text)

        # Set UI processing state
        self.status_badge.set_state("thinking")
        self.send_btn.setEnabled(False)
        self.mic_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Pause wake detector during inference
        if self.wake_detector and self.wake_detector.is_listening:
            self.wake_detector.pause()

        # Launch InferenceWorker
        self.inference_worker = InferenceWorker(self.orchestrator, user_text, parent=self)
        self.inference_worker.response_ready.connect(self._on_inference_ready)
        self.inference_worker.error.connect(self._on_inference_error)
        self.inference_worker.start()

    def _on_inference_ready(self, response_text: str, metrics: InferenceMetrics) -> None:
        self.add_message_bubble(sender="assistant", text=response_text)
        self._finish_processing()

    def _on_inference_error(self, err_msg: str) -> None:
        self.add_message_bubble(sender="system", text=err_msg)
        self._finish_processing()

    def _finish_processing(self) -> None:
        self.send_btn.setEnabled(True)
        self.mic_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # Resume wake detection
        if self.wake_detector and not self.is_wake_paused:
            self.wake_detector.resume()
            self.status_badge.set_state("wake_listening")
        else:
            self.status_badge.set_state("idle")

    def toggle_voice_turn(self) -> None:
        """Triggers or stops a manual voice interaction."""
        if self.voice_worker and self.voice_worker.isRunning():
            # Stop active recording in PTT mode
            self.voice_worker.stop_ptt_recording()
            return

        self._start_voice_turn(trigger_mode=self.ui_config.trigger_mode)

    def _on_wake_word_triggered(self) -> None:
        """Invoked when the background wake-word detector spots 'Activate David'."""
        logger.info("Wake-word triggered! Transitioning to active voice interaction...")
        self.status_badge.set_state("wake_detected")

        # Bring window to front if minimized or hidden
        if not self.isVisible() or self.isMinimized():
            self.restore_window()

        # Start active voice turn
        self._start_voice_turn(trigger_mode="vad")

    def _start_voice_turn(self, trigger_mode: str) -> None:
        """Launches VoiceTurnWorker."""
        # Pause wake-word detector to prevent microphone hardware conflict
        if self.wake_detector:
            self.wake_detector.pause()

        self.send_btn.setEnabled(False)
        self.mic_btn.setProperty("recording", "true")
        self.mic_btn.setStyle(self.mic_btn.style())
        self.mic_btn.setText("■ Stop" if trigger_mode == "ptt" else "● Listening")
        self.stop_btn.setEnabled(True)

        self.voice_worker = VoiceTurnWorker(
            voice_session=self.voice_session,
            trigger_mode=trigger_mode,
            parent=self,
        )
        self.voice_worker.status_changed.connect(self._on_voice_status_changed)
        self.voice_worker.transcription_ready.connect(self._on_voice_transcribed)
        self.voice_worker.response_ready.connect(self._on_voice_response_ready)
        self.voice_worker.error.connect(self._on_voice_error)
        self.voice_worker.finished.connect(self._on_voice_turn_finished)
        self.voice_worker.start()

    def _on_voice_status_changed(self, state: str) -> None:
        if state == "recording":
            self.status_badge.set_state("recording")
        elif state == "transcribing":
            self.status_badge.set_state("transcribing")
        elif state == "thinking":
            self.status_badge.set_state("thinking")
        elif state == "speaking":
            self.status_badge.set_state("speaking")
        elif state == "idle":
            pass

    def _on_voice_transcribed(self, transcript: str, lang: str) -> None:
        self.add_message_bubble(sender="user", text=f"{transcript} [Voice]")

    def _on_voice_response_ready(self, response_text: str, metrics: InferenceMetrics) -> None:
        self.add_message_bubble(sender="assistant", text=response_text)

    def _on_voice_error(self, err_msg: str) -> None:
        self.add_message_bubble(sender="system", text=err_msg)

    def _on_voice_turn_finished(self) -> None:
        self.mic_btn.setProperty("recording", "false")
        self.mic_btn.setStyle(self.mic_btn.style())
        self.mic_btn.setText("🎤 Speak")
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # Resume wake-word monitoring
        if self.wake_detector and not self.is_wake_paused:
            self.wake_detector.resume()
            self.status_badge.set_state("wake_listening")
        else:
            self.status_badge.set_state("idle")

    def _on_wake_word_error(self, err_msg: str) -> None:
        self.status_badge.set_state("error", "Mic Error")

    def cancel_active_operation(self) -> None:
        """Cancels active voice turn, inference, or audio playback."""
        logger.info("User requested cancellation.")
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.cancel()

        if self.voice_session:
            self.voice_session.stop_playback()

        self._finish_processing()

    def toggle_wake_word_listening(self) -> bool:
        """Toggles wake-word pause state and returns whether paused."""
        if self.is_wake_paused:
            self.resume_wake_word()
        else:
            self.pause_wake_word()
        return self.is_wake_paused

    def pause_wake_word(self) -> None:
        self.is_wake_paused = True
        if self.wake_detector:
            self.wake_detector.pause()
        self.status_badge.set_state("muted")
        self.tray.update_wake_status(is_paused=True)

    def resume_wake_word(self) -> None:
        self.is_wake_paused = False
        if self.wake_detector:
            self.wake_detector.resume()
        self.status_badge.set_state("wake_listening")
        self.tray.update_wake_status(is_paused=False)

    def open_settings(self) -> None:
        """Opens the Settings dialog."""
        dialog = SettingsDialog(
            config=self.ui_config,
            on_pause_wake_cb=self.pause_wake_word,
            on_resume_wake_cb=self.resume_wake_word,
            is_wake_paused=self.is_wake_paused,
            parent=self,
        )
        if dialog.exec():
            # Update live settings if changed
            if not self.ui_config.wake_word_enabled and self.wake_detector:
                self.wake_detector.stop()
                self.status_badge.set_state("idle")
            elif self.ui_config.wake_word_enabled and self.wake_detector:
                self.wake_detector.resume()
                self.status_badge.set_state("wake_listening")

    def restore_window(self) -> None:
        """Restores and activates the main window from tray or minimized state."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handles window close button according to tray preference."""
        if self.ui_config.minimize_to_tray_on_close:
            event.ignore()
            self.hide()
            if self._first_minimize_notification:
                self.tray.show_message(
                    "David is running in background",
                    "The assistant is listening for 'Activate David'. Click here or say the phrase to open.",
                )
                self._first_minimize_notification = False
        else:
            self.exit_application()
            event.accept()

    def exit_application(self) -> None:
        """Cleanly releases all audio hardware and terminates background workers."""
        logger.info("Exiting application cleanly...")
        if self.wake_detector:
            self.wake_detector.stop()
            self.wake_detector.unload()

        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.cancel()
            self.voice_worker.wait(1000)

        if self.voice_session:
            self.voice_session.unload()

        self.tray.hide()
        self.close()
