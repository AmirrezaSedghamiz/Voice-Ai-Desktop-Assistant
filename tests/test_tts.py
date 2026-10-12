"""
Unit tests for TTS and Playback components.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.audio.config import AudioConfig
from src.audio.playback import AudioPlaybackEngine
from src.audio.tts import PiperTtsEngine, SynthesisResult


def test_audio_config_defaults():
    config = AudioConfig()
    assert config.tts_enabled is True
    assert config.stt_enabled is True
    assert config.stt_sample_rate == 16000
    assert config.tts_sample_rate == 22050
    assert config.trigger_mode == "ptt"
    assert config.max_recording_seconds == 30


def test_tts_text_sanitization():
    raw_text = """
    Here is the response:
    ```python
    print("secret code")
    ```
    Also check `inline_code`.
    [Tool Output (get_system_status)]: {"ram": 16}
    [POLICY BLOCK] Command rejected.
    And **bold text** with [a link](https://example.com).
    """
    clean = PiperTtsEngine.sanitize_for_speech(raw_text)
    assert 'print("secret code")' not in clean
    assert "inline_code" not in clean
    assert "Tool Output" not in clean
    assert "POLICY BLOCK" not in clean
    assert "https://example.com" not in clean
    assert "bold text with a link" in clean


def test_persian_language_detection():
    persian_text = "سلام دنیا، این یک متن فارسی است."
    english_text = "Hello world, this is an English sentence."
    mixed_mostly_english = "The capital of Iran is Tehran (تهران)."

    assert PiperTtsEngine.is_persian_text(persian_text) is True
    assert PiperTtsEngine.is_persian_text(english_text) is False
    assert PiperTtsEngine.is_persian_text(mixed_mostly_english) is False


def test_tts_empty_text():
    config = AudioConfig()
    tts = PiperTtsEngine(config)
    result = tts.synthesize("   \n\t  ")
    assert result.audio_data is None
    assert result.text_spoken == ""
    assert result.language_supported is True


def test_tts_persian_suppression():
    config = AudioConfig()
    tts = PiperTtsEngine(config)
    result = tts.synthesize("پایتخت کشور ایران تهران است.")
    assert result.audio_data is None
    assert result.language_supported is False


def test_tts_missing_model_exception(tmp_path):
    config = AudioConfig(
        tts_model_path=tmp_path / "non_existent.onnx",
        tts_config_path=tmp_path / "non_existent.onnx.json",
    )
    tts = PiperTtsEngine(config)
    with pytest.raises(FileNotFoundError, match="TTS model not found"):
        tts.load_voice()


def test_playback_engine_mock():
    with patch("src.audio.playback.sd") as mock_sd:
        mock_sd.query_devices.return_value = [
            {"name": "Mock Speakers", "max_output_channels": 2, "default_samplerate": 44100},
            {"name": "Mock Mic", "max_output_channels": 0, "default_samplerate": 44100},
        ]
        player = AudioPlaybackEngine(sample_rate=22050)
        devices = player.list_output_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "Mock Speakers"

        fake_audio = np.zeros(1000, dtype=np.float32)
        success = player.play(fake_audio, blocking=True)
        assert success is True
        mock_sd.play.assert_called_once()
        mock_sd.wait.assert_called_once()
