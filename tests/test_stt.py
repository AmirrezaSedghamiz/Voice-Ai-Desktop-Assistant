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
    assert config.stt_language is None


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
