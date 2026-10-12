"""
Unit tests for AudioRecorder (Push-to-Talk and VAD).
"""

import threading
import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.audio.config import AudioConfig
from src.audio.recorder import AudioRecorder


def test_list_input_devices_mock():
    with patch("src.audio.recorder.sd") as mock_sd:
        mock_sd.query_devices.return_value = [
            {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Array Microphone", "max_input_channels": 2, "max_output_channels": 0},
        ]
        devices = AudioRecorder.list_input_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "Array Microphone"
        assert devices[0]["channels"] == 2


def test_concurrent_recording_prevention():
    config = AudioConfig()
    recorder = AudioRecorder(config)
    recorder._is_recording = True

    stop_event = threading.Event()
    with pytest.raises(RuntimeError, match="Concurrent recording session rejected"):
        recorder.record_ptt(stop_event)


def test_ptt_recording_mock():
    config = AudioConfig(stt_sample_rate=16000, max_recording_seconds=3)
    recorder = AudioRecorder(config)

    with patch("src.audio.recorder.sd.InputStream") as mock_stream_cls:
        mock_stream = MagicMock()
        mock_stream_cls.return_value.__enter__.return_value = mock_stream

        stop_event = threading.Event()

        def simulate_audio():
            time.sleep(0.1)
            # Call the callback passed to InputStream
            callback = mock_stream_cls.call_args[1]["callback"]
            dummy_chunk = np.ones((1024, 1), dtype=np.float32) * 0.05
            callback(dummy_chunk, 1024, None, None)
            stop_event.set()

        t = threading.Thread(target=simulate_audio)
        t.start()

        audio = recorder.record_ptt(stop_event)
        t.join()

        assert recorder.is_recording is False
        assert len(audio) == 1024
        assert np.isclose(audio[0], 0.05)


def test_vad_recording_cancellation_mock():
    config = AudioConfig(stt_sample_rate=16000)
    recorder = AudioRecorder(config)

    with patch("src.audio.recorder.sd.InputStream") as mock_stream_cls:
        cancel_event = threading.Event()
        cancel_event.set()  # Immediately cancelled

        result = recorder.record_vad(cancel_event=cancel_event)
        assert result is None
        assert recorder.is_recording is False
