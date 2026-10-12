"""
Audio Playback Engine: Manages speaker output, playback cancellation, and device selection.
"""

import logging
import threading
from typing import Any
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

logger = logging.getLogger("assistant.audio.playback")


class AudioPlaybackEngine:
    """Thread-safe audio player with instant stop/cancellation controls."""

    def __init__(self, output_device: int | None = None, sample_rate: int = 22050):
        self.output_device = output_device
        self.sample_rate = sample_rate
        self._lock = threading.Lock()
        self._is_playing = False

    @staticmethod
    def list_output_devices() -> list[dict[str, Any]]:
        """Enumerates available speaker and headphone output devices."""
        if sd is None:
            return []
        devices = []
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_output_channels", 0) > 0:
                    devices.append({
                        "index": idx,
                        "name": dev.get("name", f"Device {idx}"),
                        "channels": dev.get("max_output_channels", 0),
                        "default_samplerate": dev.get("default_samplerate", 44100),
                    })
        except Exception as e:
            logger.warning("Error querying audio output devices: %s", e)
        return devices

    def is_playing(self) -> bool:
        """Returns True if audio is actively playing."""
        with self._lock:
            return self._is_playing

    def stop(self) -> None:
        """Immediately halts any current audio playback."""
        with self._lock:
            if sd is not None:
                try:
                    sd.stop()
                except Exception as e:
                    logger.debug("Exception stopping sounddevice playback: %s", e)
            self._is_playing = False

    def play(self, audio_data: np.ndarray, sample_rate: int | None = None, blocking: bool = True) -> bool:
        """
        Plays an audio buffer through the selected output device.
        Automatically stops any prior utterance before beginning.
        """
        if sd is None:
            logger.error("sounddevice library is not available.")
            return False

        if audio_data is None or len(audio_data) == 0:
            return False

        sr = sample_rate or self.sample_rate

        self.stop()

        with self._lock:
            self._is_playing = True

        try:
            sd.play(audio_data, samplerate=sr, device=self.output_device)
            if blocking:
                sd.wait()
                with self._lock:
                    self._is_playing = False
            return True
        except Exception as e:
            logger.error("Playback failed: %s", e)
            with self._lock:
                self._is_playing = False
            return False
