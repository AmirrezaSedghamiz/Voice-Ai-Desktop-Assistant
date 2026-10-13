"""
Unit tests for STT (Speech-to-Text) Whisper engine.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.audio.config import AudioConfig
from src.audio.stt import WhisperSttEngine, TranscriptionResult


def test_stt_config_defaults():
    config = AudioConfig()
    assert config.stt_enabled is True
    assert config.stt_sample_rate == 16000
    assert config.stt_threads == 4
    assert config.stt_language == "fa"
    assert config.stt_initial_prompt is not None


def test_stt_empty_audio_buffer():
    config = AudioConfig()
    stt = WhisperSttEngine(config)
    empty_audio = np.array([], dtype=np.float32)

    result = stt.transcribe(empty_audio)
    assert result.is_empty is True
    assert result.text == ""
    assert result.language == "unknown"


def test_stt_silence_detection():
    config = AudioConfig()
    stt = WhisperSttEngine(config)
    # 1 second of near-zero noise
    silence = np.random.normal(0, 0.0001, 16000).astype(np.float32)

    result = stt.transcribe(silence)
    assert result.is_empty is True
    assert result.text == ""
    assert result.language == "silence"


def test_stt_missing_model_exception(tmp_path):
    config = AudioConfig(stt_model_dir=tmp_path / "missing_whisper")
    stt = WhisperSttEngine(config)
    with pytest.raises(FileNotFoundError, match="STT model files not found"):
        stt.load_model()


def test_stt_mock_transcribe():
    config = AudioConfig()
    stt = WhisperSttEngine(config)

    # Mock WhisperModel internal
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "Hello from mocked whisper"
    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.99
    mock_info.duration = 2.5

    mock_model.transcribe.return_value = ([mock_segment], mock_info)
    stt._model = mock_model
    stt._is_loaded = True

    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
    result = stt.transcribe(dummy_audio)

    assert result.is_empty is False
    assert result.text == "Hello from mocked whisper"
    assert result.language == "en"
    assert result.duration_seconds == 2.5
    assert result.language_probability == 0.99
    assert result.transcription_time_seconds >= 0


def test_stt_mock_persian_transcribe():
    config = AudioConfig(stt_language="fa")
    stt = WhisperSttEngine(config)

    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "سلام به دستیار صوتی"
    mock_info = MagicMock()
    mock_info.language = "fa"
    mock_info.language_probability = 0.95
    mock_info.duration = 3.0

    mock_model.transcribe.return_value = ([mock_segment], mock_info)
    stt._model = mock_model
    stt._is_loaded = True

    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
    result = stt.transcribe(dummy_audio)

    assert result.is_empty is False
    assert result.text == "سلام به دستیار صوتی"
    assert result.language == "fa"
    mock_model.transcribe.assert_called_once()
    assert mock_model.transcribe.call_args[1]["language"] == "fa"
    assert mock_model.transcribe.call_args[1]["task"] == "transcribe"
    assert mock_model.transcribe.call_args[1]["initial_prompt"] == config.stt_initial_prompt


def test_stt_language_auto_and_override():
    config = AudioConfig(stt_language="fa")
    stt = WhisperSttEngine(config)

    mock_model = MagicMock()
    mock_info = MagicMock(language="en", language_probability=0.99, duration=1.0)
    mock_model.transcribe.return_value = ([MagicMock(text="test")], mock_info)
    stt._model = mock_model
    stt._is_loaded = True

    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1

    # Override with auto
    stt.transcribe(dummy_audio, language="auto")
    assert mock_model.transcribe.call_args[1]["language"] is None

    # Override with en
    stt.transcribe(dummy_audio, language="en")
    assert mock_model.transcribe.call_args[1]["language"] == "en"
    assert mock_model.transcribe.call_args[1]["initial_prompt"] is None


def test_stt_long_utterance_multi_segment():
    config = AudioConfig(max_recording_seconds=120)
    stt = WhisperSttEngine(config)

    mock_model = MagicMock()
    # Simulate 3 sequential clauses across a 40-second utterance
    seg1 = MagicMock(text="This is clause one of a long thought.")
    seg2 = MagicMock(text="Here is clause two after a thinking pause.")
    seg3 = MagicMock(text="And finally clause three finishes the entire sentence.")
    info = MagicMock(language="en", language_probability=0.98, duration=42.0)

    mock_model.transcribe.return_value = ([seg1, seg2, seg3], info)
    stt._model = mock_model
    stt._is_loaded = True

    # 40 seconds of mock audio with low gain
    long_audio = np.ones(16000 * 40, dtype=np.float32) * 0.02
    result = stt.transcribe(long_audio)

    assert result.is_empty is False
    assert "clause one" in result.text
    assert "clause two" in result.text
    assert "clause three" in result.text
    assert result.duration_seconds == 42.0
    # Ensure condition_on_previous_text was set to False to prevent hallucination cascades
    assert mock_model.transcribe.call_args[1]["condition_on_previous_text"] is False
    # Ensure vad_parameters was passed with gentle silence duration
    assert mock_model.transcribe.call_args[1]["vad_parameters"]["min_silence_duration_ms"] == 1500

