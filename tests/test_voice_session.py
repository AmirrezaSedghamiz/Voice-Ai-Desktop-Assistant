"""
Unit tests for VoiceSessionManager (End-to-End Voice Integration).
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.adapter.llm_client import InferenceMetrics
from src.audio.config import AudioConfig
from src.audio.stt import TranscriptionResult
from src.audio.tts import SynthesisResult
from src.audio.voice_session import VoiceSessionManager, VoiceTurnResult


def test_voice_session_turn_success():
    mock_orchestrator = MagicMock()
    mock_metrics = InferenceMetrics()
    mock_metrics.tokens_per_second = 60.0
    mock_metrics.total_generation_time = 1.5
    mock_metrics.prompt_tokens = 20
    mock_metrics.completion_tokens = 90
    mock_orchestrator.handle_user_input.return_value = (
        "Paris is the capital of France.",
        mock_metrics,
    )

    config = AudioConfig(tts_enabled=True, stt_enabled=True)
    session = VoiceSessionManager(mock_orchestrator, config)

    # Mock STT
    session.stt = MagicMock()
    session.stt.transcribe.return_value = TranscriptionResult(
        text="What is the capital of France?",
        language="en",
        language_probability=0.98,
        duration_seconds=2.0,
        transcription_time_seconds=0.5,
        real_time_factor=0.25,
        is_empty=False,
    )

    # Mock TTS
    session.tts = MagicMock()
    fake_audio = np.ones(22050, dtype=np.float32)
    session.tts.synthesize.return_value = SynthesisResult(
        audio_data=fake_audio,
        sample_rate=22050,
        synthesis_time_seconds=0.3,
        audio_duration_seconds=1.0,
        real_time_factor=0.3,
        language_supported=True,
        text_spoken="Paris is the capital of France.",
    )

    # Mock Player
    session.player = MagicMock()

    dummy_input_audio = np.ones(16000, dtype=np.float32)
    result = session.process_voice_turn(dummy_input_audio)

    assert result.user_transcript == "What is the capital of France?"
    assert result.detected_language == "en"
    assert result.assistant_response == "Paris is the capital of France."
    assert result.spoken is True
    assert result.stt_latency_s == 0.5
    assert result.tts_latency_s == 0.3
    mock_orchestrator.handle_user_input.assert_called_once_with("What is the capital of France?")
    session.player.play.assert_called_once()


def test_voice_session_empty_speech():
    mock_orchestrator = MagicMock()
    config = AudioConfig()
    session = VoiceSessionManager(mock_orchestrator, config)

    session.stt = MagicMock()
    session.stt.transcribe.return_value = TranscriptionResult(
        text="",
        language="silence",
        language_probability=1.0,
        duration_seconds=1.0,
        transcription_time_seconds=0.0,
        real_time_factor=0.0,
        is_empty=True,
    )

    dummy_audio = np.zeros(16000, dtype=np.float32)
    result = session.process_voice_turn(dummy_audio)

    assert result.user_transcript == ""
    assert result.spoken is False
    assert result.assistant_response == "[No speech detected]"
    mock_orchestrator.handle_user_input.assert_not_called()


def test_voice_session_tts_disabled():
    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_user_input.return_value = ("Hello text only", None)

    config = AudioConfig(tts_enabled=False)
    session = VoiceSessionManager(mock_orchestrator, config)

    session.stt = MagicMock()
    session.stt.transcribe.return_value = TranscriptionResult(
        text="Hello",
        language="en",
        language_probability=0.99,
        duration_seconds=1.0,
        transcription_time_seconds=0.2,
        real_time_factor=0.2,
        is_empty=False,
    )

    session.tts = MagicMock()
    session.player = MagicMock()

    dummy_audio = np.ones(16000, dtype=np.float32)
    result = session.process_voice_turn(dummy_audio)

    assert result.spoken is False
    assert result.assistant_response == "Hello text only"
    session.tts.synthesize.assert_not_called()
    session.player.play.assert_not_called()
