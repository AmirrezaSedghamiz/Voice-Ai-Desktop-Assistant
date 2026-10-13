"""
Automated UI and Integration Tests for David Desktop Assistant.
Tests widget rendering, RTL/LTR bi-directional text, settings persistence,
signal-slot worker flows, and main window lifecycle headlessly using offscreen Qt platform.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Ensure Qt runs headlessly in offscreen mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.adapter.llm_client import InferenceMetrics
from src.ui.config import UiConfig
from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.widgets import (
    ChatBubbleWidget,
    EmptyStateWidget,
    StatusBadgeWidget,
    format_chat_html,
    is_persian_text,
)


@pytest.fixture(scope="session")
def qapp():
    """Provides a singleton QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ui_config_persistence(tmp_path: Path):
    """Tests saving and loading UI settings from JSON."""
    cfg_file = tmp_path / "test_settings.json"
    cfg = UiConfig(
        assistant_name="David Test",
        wake_word_enabled=False,
        trigger_mode="ptt",
        tts_enabled=False,
    )
    cfg.save(cfg_file)
    assert cfg_file.exists()

    loaded = UiConfig.load(cfg_file)
    assert loaded.assistant_name == "David Test"
    assert loaded.wake_word_enabled is False
    assert loaded.trigger_mode == "ptt"
    assert loaded.tts_enabled is False


def test_persian_text_detection():
    """Tests detection of Persian characters."""
    assert is_persian_text("سلام، چطوری؟") is True
    assert is_persian_text("یک تسک جدید برای فردا بساز") is True
    assert is_persian_text("Hello, how are you?") is False
    assert is_persian_text("Open notepad") is False
    # Mixed Persian with English word
    assert is_persian_text("فایل main.py رو باز کن") is True


def test_format_chat_html_rtl_and_ltr():
    """Tests that Persian text produces RTL html and English produces LTR."""
    en_html = format_chat_html("Hello world", is_persian=False)
    assert 'dir="ltr"' in en_html
    assert "Hello world" in en_html

    fa_html = format_chat_html("سلام دنیا", is_persian=True)
    assert 'dir="rtl"' in fa_html
    assert "سلام دنیا" in fa_html

    # Code snippet wrapping
    code_html = format_chat_html("اجرای `python test.py` برای آزمایش", is_persian=True)
    assert 'dir="rtl"' in code_html
    assert '<code dir="ltr"' in code_html
    assert "python test.py" in code_html


def test_chat_bubble_widget(qapp):
    """Tests ChatBubbleWidget instantiation for user, assistant, and Persian text."""
    bubble_user = ChatBubbleWidget(sender="user", text="Open Notepad")
    assert bubble_user.sender == "user"
    assert bubble_user.is_persian is False

    bubble_asst = ChatBubbleWidget(sender="assistant", text="Notepad opened.")
    assert bubble_asst.sender == "assistant"

    bubble_fa = ChatBubbleWidget(sender="user", text="سلام دیوید")
    assert bubble_fa.is_persian is True


def test_status_badge_widget(qapp):
    """Tests StatusBadgeWidget state transitions."""
    badge = StatusBadgeWidget()
    assert "Idle" in badge.text() or "Ready" in badge.text()

    badge.set_state("wake_listening")
    assert "Listening" in badge.text()

    badge.set_state("recording")
    assert "Recording" in badge.text()

    badge.set_state("thinking")
    assert "Processing" in badge.text()


def test_empty_state_suggestion_signal(qapp):
    """Tests that clicking suggestion buttons emits suggestion_clicked signal."""
    widget = EmptyStateWidget()
    clicked_texts = []
    widget.suggestion_clicked.connect(lambda t: clicked_texts.append(t))

    # Trigger first suggestion button
    buttons = widget.findChildren(EmptyStateWidget.SUGGESTIONS[0].__class__)
    # Find QPushButton children
    from PySide6.QtWidgets import QPushButton
    btns = widget.findChildren(QPushButton)
    assert len(btns) >= 4
    btns[0].click()

    assert len(clicked_texts) == 1
    assert clicked_texts[0] == EmptyStateWidget.SUGGESTIONS[0]


def test_settings_dialog(qapp, tmp_path: Path):
    """Tests SettingsDialog loads configuration and accepts changes."""
    cfg = UiConfig(wake_word_enabled=True)
    dialog = SettingsDialog(config=cfg)
    assert dialog.ww_checkbox.isChecked() is True

    # Change settings
    dialog.ww_checkbox.setChecked(False)
    dialog.tts_checkbox.setChecked(False)
    dialog._save_and_accept()

    assert cfg.wake_word_enabled is False
    assert cfg.tts_enabled is False


def test_main_window_text_flow_and_lifecycle(qapp, tmp_path: Path):
    """Tests MainWindow text message input, mock inference, and bubble insertion."""
    # Mock orchestrator
    mock_orchestrator = MagicMock()
    mock_metrics = InferenceMetrics()
    mock_metrics.total_generation_time = 0.1
    mock_orchestrator.handle_user_input.return_value = ("I can help with that.", mock_metrics)

    # Mock voice session
    mock_voice_session = MagicMock()
    mock_voice_session.config.max_recording_seconds = 10
    mock_voice_session.config.tts_enabled = False

    cfg = UiConfig(wake_word_enabled=False)  # disable live audio capture in headless test

    window = MainWindow(
        orchestrator=mock_orchestrator,
        voice_session=mock_voice_session,
        ui_config=cfg,
    )
    window.show()

    # Verify initial state
    assert window.windowTitle() == "David - Local AI Assistant"
    assert window.empty_state.isVisible() is True

    # Simulate entering text and sending
    window.text_input.setPlainText("Hello David")
    window.send_text_message()

    # Wait for background thread worker to complete and process queued events
    if window.inference_worker:
        window.inference_worker.wait(3000)
    qapp.processEvents()

    # Verify mock orchestrator called
    mock_orchestrator.handle_user_input.assert_called_with("Hello David")

    # Verify empty state hidden and message bubbles added
    assert window.empty_state.isHidden() is True
    bubbles = window.conversation_widget.findChildren(ChatBubbleWidget)
    assert len(bubbles) == 2  # 1 user + 1 assistant
    assert bubbles[0].raw_text == "Hello David"
    assert bubbles[1].raw_text == "I can help with that."

    # Test clean exit
    window.exit_application()


def test_voice_turn_worker_lifecycle(qapp):
    """Tests VoiceTurnWorker execution through recording, transcription, reasoning, and TTS."""
    from src.audio.stt import TranscriptionResult
    from src.audio.tts import SynthesisResult
    import numpy as np

    mock_voice_session = MagicMock()
    mock_voice_session.config.max_recording_seconds = 10
    mock_voice_session.config.tts_enabled = True

    # 1. Mock recording returns audio samples
    fake_audio = np.zeros(16000, dtype=np.float32)
    mock_voice_session.recorder.record_vad.return_value = fake_audio

    # 2. Mock STT returns transcript
    mock_voice_session.stt.transcribe.return_value = TranscriptionResult(
        text="یادآوری برای جلسه فردا بذار",
        language="fa",
        language_probability=0.98,
        duration_seconds=1.0,
        transcription_time_seconds=0.2,
        real_time_factor=0.2,
        is_empty=False,
    )

    # 3. Mock Orchestrator returns response
    mock_metrics = InferenceMetrics()
    mock_metrics.total_generation_time = 0.3
    mock_voice_session.orchestrator.handle_user_input.return_value = ("یادآوری شما ثبت شد.", mock_metrics)

    # 4. Mock TTS returns audio
    mock_voice_session.tts.synthesize.return_value = SynthesisResult(
        audio_data=np.zeros(22050, dtype=np.float32),
        sample_rate=22050,
        synthesis_time_seconds=0.1,
        audio_duration_seconds=1.0,
        real_time_factor=0.1,
        language_supported=True,
        text_spoken="یادآوری شما ثبت شد.",
    )

    from src.ui.workers import VoiceTurnWorker

    worker = VoiceTurnWorker(mock_voice_session, trigger_mode="vad")

    statuses = []
    transcripts = []
    responses = []
    finished_called = []

    worker.status_changed.connect(lambda s: statuses.append(s))
    worker.transcription_ready.connect(lambda t, l: transcripts.append((t, l)))
    worker.response_ready.connect(lambda r, m: responses.append(r))
    worker.finished.connect(lambda: finished_called.append(True))

    worker.start()
    worker.wait(4000)
    qapp.processEvents()

    assert "recording" in statuses
    assert "transcribing" in statuses
    assert "thinking" in statuses
    assert "speaking" in statuses
    assert "idle" in statuses

    assert len(transcripts) == 1
    assert transcripts[0][0] == "یادآوری برای جلسه فردا بذار"
    assert transcripts[0][1] == "fa"

    assert len(responses) == 1
    assert responses[0] == "یادآوری شما ثبت شد."
    assert len(finished_called) == 1


def test_wake_word_trigger_transitions_main_window(qapp):
    """Tests that a wake-word trigger event transitions status and starts active voice interaction."""
    mock_orchestrator = MagicMock()
    mock_voice_session = MagicMock()
    mock_voice_session.config.max_recording_seconds = 10
    mock_voice_session.config.tts_enabled = False

    cfg = UiConfig(wake_word_enabled=False)
    window = MainWindow(
        orchestrator=mock_orchestrator,
        voice_session=mock_voice_session,
        ui_config=cfg,
    )
    window.show()

    with patch.object(window, "_start_voice_turn") as mock_start_turn:
        window._on_wake_word_triggered()
        assert window.status_badge.text() == "Wake Phrase Detected!"
        mock_start_turn.assert_called_once_with(trigger_mode="vad")

    window.exit_application()


def test_main_window_cancellation(qapp):
    """Tests cancel_active_operation stops active voice worker and audio playback."""
    mock_orchestrator = MagicMock()
    mock_voice_session = MagicMock()
    mock_voice_session.config.max_recording_seconds = 10

    cfg = UiConfig(wake_word_enabled=False)
    window = MainWindow(
        orchestrator=mock_orchestrator,
        voice_session=mock_voice_session,
        ui_config=cfg,
    )
    window.show()

    # Create dummy active worker
    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    window.voice_worker = mock_worker

    window.cancel_active_operation()
    mock_worker.cancel.assert_called_once()
    mock_voice_session.stop_playback.assert_called_once()

    window.exit_application()

