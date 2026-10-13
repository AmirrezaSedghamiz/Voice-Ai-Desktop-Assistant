"""
Quality Lab Suite: Desktop GUI & Windows Lifecycle Evaluation Suite.
Tests PySide6 UI responsiveness headlessly with offscreen platform,
bi-directional RTL/LTR text rendering, async worker lifecycle, cancellation, and clean shutdown.
"""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from quality_lab.config import QualityLabConfig
from quality_lab.fixtures.mock_environment import DisposableSandbox
from quality_lab.models import FailureCategory, Severity, SuiteResult, TestMode, TestResult, TestStatus
from src.adapter.llm_client import InferenceMetrics
from src.ui.config import UiConfig
from src.ui.main_window import MainWindow
from src.ui.widgets import ChatBubbleWidget, StatusBadgeWidget, format_chat_html, is_persian_text


class GuiSuite:
    """Evaluates desktop GUI widgets, offscreen rendering, and worker lifecycles."""

    def __init__(self, config: QualityLabConfig):
        self.config = config
        self._qapp = QApplication.instance() or QApplication([])

    def run(self) -> SuiteResult:
        suite = SuiteResult(suite_name="gui", status=TestStatus.PASSED)
        cases = [
            self._test_persian_rtl_and_english_ltr_html_rendering,
            self._test_status_badge_state_machine,
            self._test_chat_bubble_widget_creation,
            self._test_main_window_text_flow_and_bubble_insertion,
            self._test_main_window_cancellation_flow,
            self._test_voice_turn_worker_signal_contracts,
        ]

        for case_fn in cases:
            res = case_fn()
            suite.results.append(res)

        suite.recompute_summary()
        return suite

    def _test_persian_rtl_and_english_ltr_html_rendering(self) -> TestResult:
        start_t = time.time()
        test_id = "GUI-WIDGET-RTL-001"
        name = "Bi-directional RTL / LTR HTML Formatting"
        try:
            en_html = format_chat_html("Hello world, this is English text.", is_persian=False)
            assert 'dir="ltr"' in en_html

            fa_html = format_chat_html("سلام دیوید، این متن فارسی است.", is_persian=True)
            assert 'dir="rtl"' in fa_html

            # Inline code inside Persian must preserve LTR
            mixed_code = format_chat_html("دستور `python run.py` را اجرا کن", is_persian=True)
            assert 'dir="rtl"' in mixed_code
            assert '<code dir="ltr"' in mixed_code

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Correct dir attribute for Persian RTL and English LTR",
                observed_outcome="HTML direction tags verified",
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_status_badge_state_machine(self) -> TestResult:
        start_t = time.time()
        test_id = "GUI-STATUS-BADGE-002"
        name = "StatusBadgeWidget State Transitions"
        try:
            badge = StatusBadgeWidget()
            assert "Idle" in badge.text() or "Ready" in badge.text()

            badge.set_state("wake_listening")
            assert "Listening" in badge.text()

            badge.set_state("recording")
            assert "Recording" in badge.text()

            badge.set_state("thinking")
            assert "Processing" in badge.text()

            badge.set_state("speaking")
            assert "Speaking" in badge.text()

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Badge transitions across all operational assistant states",
                observed_outcome="All state strings and badges verified",
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )

    def _test_chat_bubble_widget_creation(self) -> TestResult:
        start_t = time.time()
        test_id = "GUI-CHAT-BUBBLE-003"
        name = "ChatBubbleWidget Creation and Script Binding"
        try:
            user_bubble = ChatBubbleWidget(sender="user", text="Open Notepad")
            assert user_bubble.sender == "user"
            assert user_bubble.is_persian is False

            fa_bubble = ChatBubbleWidget(sender="user", text="سلام دیوید")
            assert fa_bubble.is_persian is True

            asst_bubble = ChatBubbleWidget(sender="assistant", text="Notepad opened.")
            assert asst_bubble.sender == "assistant"

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="User and assistant bubbles instantiate with correct script styles",
                observed_outcome="Chat bubbles validated",
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )

    def _test_main_window_text_flow_and_bubble_insertion(self) -> TestResult:
        start_t = time.time()
        test_id = "GUI-WINDOW-TEXT-FLOW-004"
        name = "MainWindow Text Flow & Asynchronous Message Insertion"
        try:
            mock_orch = MagicMock()
            metrics = InferenceMetrics()
            metrics.total_generation_time = 0.05
            mock_orch.handle_user_input.return_value = ("I can assist with tasks.", metrics)

            mock_voice = MagicMock()
            mock_voice.config.max_recording_seconds = 10
            mock_voice.config.tts_enabled = False

            cfg = UiConfig(wake_word_enabled=False)

            window = MainWindow(
                orchestrator=mock_orch,
                voice_session=mock_voice,
                ui_config=cfg,
            )
            window.show()

            # Input and send text
            window.text_input.setPlainText("Hello David")
            window.send_text_message()

            if window.inference_worker:
                window.inference_worker.wait(2000)
            self._qapp.processEvents()

            bubbles = window.conversation_widget.findChildren(ChatBubbleWidget)
            assert len(bubbles) == 2
            assert bubbles[0].raw_text == "Hello David"
            assert bubbles[1].raw_text == "I can assist with tasks."

            window.exit_application()

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="User & assistant messages rendered asynchronously in scroll area",
                observed_outcome=f"2 message bubbles inserted successfully",
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_main_window_cancellation_flow(self) -> TestResult:
        start_t = time.time()
        test_id = "GUI-WINDOW-CANCEL-005"
        name = "MainWindow User Cancellation Responsiveness"
        try:
            mock_orch = MagicMock()
            mock_voice = MagicMock()
            cfg = UiConfig(wake_word_enabled=False)

            window = MainWindow(
                orchestrator=mock_orch,
                voice_session=mock_voice,
                ui_config=cfg,
            )
            window.show()

            # Attach mock worker
            mock_worker = MagicMock()
            mock_worker.isRunning.return_value = True
            window.voice_worker = mock_worker

            # Trigger cancellation
            window.cancel_active_operation()
            mock_worker.cancel.assert_called_once()
            mock_voice.stop_playback.assert_called_once()

            window.exit_application()

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Active worker cancelled and audio stopped without freezing UI",
                observed_outcome="Worker cancelled and playback stopped cleanly",
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_voice_turn_worker_signal_contracts(self) -> TestResult:
        start_t = time.time()
        test_id = "GUI-WORKER-SIGNALS-006"
        name = "VoiceTurnWorker QThread Signal-Slot Contract"
        try:
            from src.audio.stt import TranscriptionResult
            from src.audio.tts import SynthesisResult
            from src.ui.workers import VoiceTurnWorker
            import numpy as np

            mock_session = MagicMock()
            mock_session.config.max_recording_seconds = 5
            mock_session.config.tts_enabled = False
            mock_session.recorder.record_vad.return_value = np.zeros(16000, dtype=np.float32)

            mock_session.stt.transcribe.return_value = TranscriptionResult(
                text="سلام",
                language="fa",
                language_probability=0.99,
                duration_seconds=1.0,
                transcription_time_seconds=0.1,
                real_time_factor=0.1,
                is_empty=False,
            )

            metrics = InferenceMetrics()
            mock_session.orchestrator.handle_user_input.return_value = ("سلام، چطورید؟", metrics)

            worker = VoiceTurnWorker(mock_session, trigger_mode="vad")
            statuses = []
            worker.status_changed.connect(lambda s: statuses.append(s))

            worker.start()
            worker.wait(2000)
            self._qapp.processEvents()

            assert "recording" in statuses
            assert "transcribing" in statuses
            assert "thinking" in statuses
            assert "idle" in statuses

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="VoiceTurnWorker emits recording -> transcribing -> thinking -> idle",
                observed_outcome=f"Observed states: {statuses}",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="gui",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )
