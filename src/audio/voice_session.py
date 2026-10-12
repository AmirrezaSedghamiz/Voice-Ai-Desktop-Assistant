"""
Voice Session Manager: Connects Audio Capture -> STT -> Orchestrator -> TTS -> Playback.
Maintains strict sequential scheduling and enforces policy checks and safety guards.
"""

import logging
import threading
from typing import Callable, NamedTuple
import numpy as np

from src.adapter.llm_client import InferenceMetrics
from src.agent.orchestrator import SafeAgentOrchestrator
from src.audio.config import AudioConfig
from src.audio.playback import AudioPlaybackEngine
from src.audio.recorder import AudioRecorder
from src.audio.stt import WhisperSttEngine
from src.audio.tts import PiperTtsEngine

logger = logging.getLogger("assistant.audio.session")


class VoiceTurnResult(NamedTuple):
    user_transcript: str
    detected_language: str
    assistant_response: str
    spoken: bool
    stt_latency_s: float
    tts_latency_s: float
    llm_metrics: InferenceMetrics | None


class VoiceSessionManager:
    """Orchestrates sequential, resource-governed voice interaction turns."""

    def __init__(
        self,
        orchestrator: SafeAgentOrchestrator,
        config: AudioConfig,
    ):
        self.orchestrator = orchestrator
        self.config = config

        self.recorder = AudioRecorder(config)
        self.stt = WhisperSttEngine(config)
        self.tts = PiperTtsEngine(config)
        self.player = AudioPlaybackEngine(
            output_device=config.output_device_index,
            sample_rate=config.tts_sample_rate,
        )

    def initialize_models(self) -> None:
        """Pre-loads local STT and TTS models."""
        logger.info("Initializing voice models...")
        if self.config.stt_enabled and not self.stt.is_loaded:
            self.stt.load_model()
        if self.config.tts_enabled and not self.tts.is_loaded:
            self.tts.load_voice()

    def process_voice_turn(
        self,
        audio_data: np.ndarray,
        on_transcribed_callback: Callable[[str, str], None] | None = None,
        on_assistant_response_callback: Callable[[str], None] | None = None,
    ) -> VoiceTurnResult:
        """
        Executes a single sequential voice turn:
        1. Transcribe audio using faster-whisper (CPU INT8)
        2. Feed text into existing SafeAgentOrchestrator
        3. Synthesize response using Piper (CPU)
        4. Play audio through speakers
        """
        # Step 1: Transcribe
        stt_result = self.stt.transcribe(audio_data)

        if stt_result.is_empty or not stt_result.text.strip():
            logger.info("Voice turn aborted: No intelligible speech recognized.")
            return VoiceTurnResult(
                user_transcript="",
                detected_language="none",
                assistant_response="[No speech detected]",
                spoken=False,
                stt_latency_s=stt_result.transcription_time_seconds,
                tts_latency_s=0.0,
                llm_metrics=None,
            )

        transcript_text = stt_result.text.strip()
        lang = stt_result.language

        if on_transcribed_callback:
            on_transcribed_callback(transcript_text, lang)

        # Step 2: Feed into existing Orchestrator
        response_text, metrics = self.orchestrator.handle_user_input(transcript_text)

        if on_assistant_response_callback:
            on_assistant_response_callback(response_text)

        # Step 3: Text-to-Speech synthesis (if enabled)
        spoken = False
        tts_latency = 0.0

        if self.config.tts_enabled:
            synth = self.tts.synthesize(response_text)
            tts_latency = synth.synthesis_time_seconds

            if synth.audio_data is not None and len(synth.audio_data) > 0:
                # Step 4: Playback
                self.player.play(synth.audio_data, sample_rate=synth.sample_rate, blocking=True)
                spoken = True
            elif not synth.language_supported:
                logger.info("Spoken response skipped because text language is not supported by current voice model.")

        return VoiceTurnResult(
            user_transcript=transcript_text,
            detected_language=lang,
            assistant_response=response_text,
            spoken=spoken,
            stt_latency_s=stt_result.transcription_time_seconds,
            tts_latency_s=tts_latency,
            llm_metrics=metrics,
        )

    def stop_playback(self) -> None:
        """Stops active speech immediately."""
        self.player.stop()

    def unload(self) -> None:
        """Releases audio models from RAM."""
        self.stop_playback()
        self.stt.unload_model()
        self.tts.unload_voice()
