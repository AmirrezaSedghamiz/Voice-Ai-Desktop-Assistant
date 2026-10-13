"""
Asynchronous Qt Workers for David Assistant:
- InferenceWorker: Executes LLM inference and tool orchestration off the GUI thread.
- VoiceTurnWorker: Orchestrates microphone capture, STT, LLM reasoning, and TTS playback.
- WakeWordWorker: Runs the continuous offline keyword spotter in background.
"""

import logging
import threading
from typing import Any
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from src.adapter.llm_client import InferenceMetrics
from src.agent.orchestrator import SafeAgentOrchestrator
from src.audio.voice_session import VoiceSessionManager
from src.audio.wake_word import WakeWordDetector

logger = logging.getLogger("assistant.ui.workers")


class InferenceWorker(QThread):
    """Executes a text request through SafeAgentOrchestrator on a background worker thread."""

    response_ready = Signal(str, object)  # response_text, InferenceMetrics
    error = Signal(str)

    def __init__(
        self,
        orchestrator: SafeAgentOrchestrator,
        user_text: str,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.user_text = user_text

    def run(self) -> None:
        try:
            logger.info("Executing background inference for user text...")
            response_text, metrics = self.orchestrator.handle_user_input(self.user_text)
            self.response_ready.emit(response_text, metrics)
        except Exception as e:
            logger.error("Exception during background inference: %s", e, exc_info=True)
            self.error.emit(f"Error processing request: {e}")


class VoiceTurnWorker(QThread):
    """
    Executes a complete voice interaction turn:
    Record audio -> Transcribe (Whisper) -> Reason (Orchestrator) -> Synthesize (Piper) -> Play.
    Ensures safe cancellation and strict hardware cleanup.
    """

    status_changed = Signal(str)  # "recording" | "transcribing" | "thinking" | "speaking" | "idle"
    transcription_ready = Signal(str, str)  # transcript_text, detected_language
    response_ready = Signal(str, object)  # response_text, InferenceMetrics
    error = Signal(str)

    def __init__(
        self,
        voice_session: VoiceSessionManager,
        trigger_mode: str = "vad",  # "vad" or "ptt"
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.voice_session = voice_session
        self.trigger_mode = trigger_mode
        self._cancel_event = threading.Event()
        self._stop_ptt_event = threading.Event()

    def cancel(self) -> None:
        """Immediately interrupts active recording, inference, or audio playback."""
        logger.info("Voice turn cancelled by user.")
        self._cancel_event.set()
        self._stop_ptt_event.set()
        try:
            self.voice_session.stop_playback()
        except Exception:
            pass

    def stop_ptt_recording(self) -> None:
        """Signals the manual Push-to-Talk recorder to finish capturing speech."""
        self._stop_ptt_event.set()

    def run(self) -> None:
        try:
            # 1. Capture Microphone Audio
            self.status_changed.emit("recording")
            audio_data: np.ndarray | None = None

            if self.trigger_mode == "ptt":
                audio_data = self.voice_session.recorder.record_ptt(
                    stop_event=self._stop_ptt_event,
                    max_duration_seconds=self.voice_session.config.max_recording_seconds,
                )
            else:
                # VAD mode
                audio_data = self.voice_session.recorder.record_vad(
                    cancel_event=self._cancel_event,
                    max_duration_seconds=self.voice_session.config.max_recording_seconds,
                )

            if self._cancel_event.is_set():
                return

            if audio_data is None or len(audio_data) == 0:
                logger.info("No audio captured in voice turn.")
                return

            # 2. Speech-to-Text Transcription
            self.status_changed.emit("transcribing")
            stt_result = self.voice_session.stt.transcribe(audio_data)

            if self._cancel_event.is_set():
                return

            transcript = stt_result.text.strip()
            lang = stt_result.language
            if not transcript or stt_result.is_empty:
                logger.info("Voice turn completed: no intelligible speech detected.")
                return

            self.transcription_ready.emit(transcript, lang)

            # 3. Agent Reasoning & Tool Orchestration
            self.status_changed.emit("thinking")
            response_text, metrics = self.voice_session.orchestrator.handle_user_input(transcript)

            if self._cancel_event.is_set():
                return

            self.response_ready.emit(response_text, metrics)

            # 4. Text-to-Speech Playback (if enabled)
            if self.voice_session.config.tts_enabled and not self._cancel_event.is_set():
                self.status_changed.emit("speaking")
                synth = self.voice_session.tts.synthesize(response_text)
                if synth.audio_data is not None and len(synth.audio_data) > 0 and not self._cancel_event.is_set():
                    self.voice_session.player.play(synth.audio_data, sample_rate=synth.sample_rate, blocking=True)

        except Exception as e:
            logger.error("Error in VoiceTurnWorker: %s", e, exc_info=True)
            self.error.emit(f"Voice turn error: {e}")
        finally:
            self.status_changed.emit("idle")


class WakeWordWorker(QThread):
    """
    Manages continuous background keyword spotting for 'Activate David'.
    Communicates detection events back to the Qt main thread via signals.
    """

    wake_word_detected = Signal()
    error = Signal(str)

    def __init__(self, detector: WakeWordDetector, parent: QObject | None = None):
        super().__init__(parent)
        self.detector = detector

    def run(self) -> None:
        try:
            self.detector.start(
                on_detected=self._on_detected,
                on_error=self._on_error,
            )
        except Exception as e:
            logger.error("Failed to start wake-word detector: %s", e)
            self.error.emit(str(e))

    def _on_detected(self) -> None:
        logger.info("WakeWordWorker received detection callback; emitting Qt signal.")
        self.wake_word_detected.emit()

    def _on_error(self, err_msg: str) -> None:
        logger.warning("WakeWordWorker error: %s", err_msg)
        self.error.emit(err_msg)

    def pause_listening(self) -> None:
        self.detector.pause()

    def resume_listening(self) -> None:
        self.detector.resume()

    def stop_listening(self) -> None:
        self.detector.stop()
