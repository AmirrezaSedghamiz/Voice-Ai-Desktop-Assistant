"""
Audio Recorder Engine: Microphone capture, Push-to-Talk (PTT), and Voice Activity Detection (VAD).
Ensures bounded buffers, immediate hardware release, and zero network transmission.
"""

import collections
import logging
import threading
import time
from typing import Any, Callable
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

from src.audio.config import AudioConfig

logger = logging.getLogger("assistant.audio.recorder")


class AudioRecorder:
    """Manages microphone audio capture with Push-to-Talk and VAD triggers."""

    def __init__(self, config: AudioConfig):
        self.config = config
        self._lock = threading.Lock()
        self._is_recording = False

    @staticmethod
    def list_input_devices() -> list[dict[str, Any]]:
        """Enumerates available microphone input devices."""
        if sd is None:
            return []
        devices = []
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    devices.append({
                        "index": idx,
                        "name": dev.get("name", f"Device {idx}"),
                        "channels": dev.get("max_input_channels", 0),
                        "default_samplerate": dev.get("default_samplerate", 44100),
                    })
        except Exception as e:
            logger.warning("Error querying audio input devices: %s", e)
        return devices

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def record_ptt(
        self,
        stop_event: threading.Event,
        on_start_callback: Callable[[], None] | None = None,
        max_duration_seconds: float | None = None,
    ) -> np.ndarray:
        """
        Records microphone audio until stop_event is set or max_duration is reached.
        Microphone is strictly acquired at start and released immediately upon termination.
        """
        if sd is None:
            raise RuntimeError("sounddevice is not available.")

        with self._lock:
            if self._is_recording:
                raise RuntimeError("Concurrent recording session rejected. Microphone is already in use.")
            self._is_recording = True

        max_sec = max_duration_seconds or self.config.max_recording_seconds
        sr = self.config.stt_sample_rate
        max_samples = int(max_sec * sr)

        audio_chunks: list[np.ndarray] = []
        total_samples = 0

        def callback(indata, frames, time_info, status):
            nonlocal total_samples
            if status:
                logger.debug("Input stream status: %s", status)
            if total_samples < max_samples:
                chunk = indata[:, 0].copy()  # Mono channel
                audio_chunks.append(chunk)
                total_samples += len(chunk)
            else:
                stop_event.set()

        try:
            if on_start_callback:
                on_start_callback()

            logger.info("Opening microphone stream (Device: %s, SR: %d Hz)", self.config.input_device_index, sr)
            with sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
                device=self.config.input_device_index,
                blocksize=1024,
                callback=callback,
            ):
                while not stop_event.is_set():
                    time.sleep(0.05)

        finally:
            with self._lock:
                self._is_recording = False
            logger.info("Microphone stream closed and released.")

        if not audio_chunks:
            return np.array([], dtype=np.float32)

        full_audio = np.concatenate(audio_chunks)
        return full_audio[:max_samples]

    def record_vad(
        self,
        cancel_event: threading.Event | None = None,
        on_speech_start: Callable[[], None] | None = None,
        silence_timeout_ms: int | None = None,
        energy_threshold: float | None = None,
        max_duration_seconds: float | None = None,
    ) -> np.ndarray | None:
        """
        Monitors microphone with lightweight energy-based VAD.
        Captures audio with pre-roll once speech onset is detected,
        and terminates when silence exceeds the threshold.
        """
        if sd is None:
            raise RuntimeError("sounddevice is not available.")

        with self._lock:
            if self._is_recording:
                raise RuntimeError("Concurrent recording session rejected.")
            self._is_recording = True

        sr = self.config.stt_sample_rate
        max_sec = max_duration_seconds or self.config.max_recording_seconds
        silence_limit = (silence_timeout_ms or self.config.vad_silence_duration_ms) / 1000.0
        threshold = energy_threshold or self.config.vad_energy_threshold

        frame_ms = 30
        frame_size = int(sr * frame_ms / 1000)

        # Pre-roll ring buffer: 300ms of audio
        preroll_frames = int(300 / frame_ms)
        preroll_buffer = collections.deque(maxlen=preroll_frames)

        recorded_chunks: list[np.ndarray] = []
        speech_started = False
        silence_duration = 0.0
        start_time = time.time()

        raw_frames_queue = collections.deque()

        def callback(indata, frames, time_info, status):
            raw_frames_queue.append(indata[:, 0].copy())

        try:
            logger.info("Starting VAD microphone monitor...")
            with sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
                device=self.config.input_device_index,
                blocksize=frame_size,
                callback=callback,
            ):
                while True:
                    if cancel_event and cancel_event.is_set():
                        logger.info("VAD recording cancelled by user.")
                        return None

                    if time.time() - start_time > max_sec:
                        logger.info("VAD reached maximum recording duration (%ds).", max_sec)
                        break

                    while raw_frames_queue:
                        frame = raw_frames_queue.popleft()
                        rms = float(np.sqrt(np.mean(frame**2)))

                        if not speech_started:
                            preroll_buffer.append(frame)
                            if rms >= threshold:
                                speech_started = True
                                logger.info("Speech onset detected (RMS: %.4f >= %.4f)", rms, threshold)
                                if on_speech_start:
                                    on_speech_start()
                                # Drain pre-roll into recording
                                recorded_chunks.extend(preroll_buffer)
                                recorded_chunks.append(frame)
                        else:
                            recorded_chunks.append(frame)
                            if rms < threshold:
                                silence_duration += (len(frame) / sr)
                                if silence_duration >= silence_limit:
                                    logger.info("Silence detected (%.2fs). Ending utterance.", silence_duration)
                                    return np.concatenate(recorded_chunks)
                            else:
                                silence_duration = 0.0

                    time.sleep(0.02)

        finally:
            with self._lock:
                self._is_recording = False
            logger.info("VAD microphone monitor closed and released.")

        if speech_started and recorded_chunks:
            return np.concatenate(recorded_chunks)
        return None
