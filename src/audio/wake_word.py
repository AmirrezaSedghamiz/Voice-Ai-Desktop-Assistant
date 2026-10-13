"""
Wake-Word Detection Engine: Lightweight offline keyword spotting for 'Activate David'.
Uses Vosk KaldiRecognizer with constrained grammar, zero cloud transmission,
and two-stage RMS energy gating to keep idle CPU usage minimal.
"""

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Callable
import numpy as np
from pydantic import BaseModel, Field

try:
    import vosk
except ImportError:
    vosk = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

logger = logging.getLogger("assistant.audio.wake_word")

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class WakeWordConfig(BaseModel):
    """Configuration for local wake-word monitoring."""

    phrase: str = Field(default="activate david", description="Configured activation phrase.")
    model_dir: Path = Field(
        default=PROJECT_ROOT / "models" / "wake_word" / "vosk-model-small-en-us-0.15",
        description="Path to local quantized Vosk acoustic model directory.",
    )
    sample_rate: int = Field(default=16000, description="Audio sampling rate (Hz) for keyword recognizer.")
    block_size: int = Field(default=4000, description="Audio buffer block size in samples (0.25s at 16kHz).")
    energy_threshold: float = Field(
        default=0.010,
        ge=0.001,
        le=0.5,
        description="Minimum RMS audio energy before invoking acoustic recognizer.",
    )
    cooldown_seconds: float = Field(
        default=2.5,
        ge=0.5,
        le=10.0,
        description="Debounce duration in seconds to prevent immediate re-trigger.",
    )
    enabled: bool = Field(default=True, description="Whether background wake-word listening is enabled.")
    input_device_index: int | None = Field(
        default=None,
        description="Microphone input device index (None = system default).",
    )


class WakeWordDetector:
    """Offline, resource-efficient background keyword spotter."""

    def __init__(self, config: WakeWordConfig | None = None):
        self.config = config or WakeWordConfig()
        self._model = None
        self._recognizer = None
        self._is_loaded = False
        self._is_listening = False
        self._is_paused = False
        self._stream = None
        self._lock = threading.Lock()
        self._last_trigger_time: float = 0.0
        self._on_detected_callback: Callable[[], None] | None = None
        self._on_error_callback: Callable[[str], None] | None = None

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def is_listening(self) -> bool:
        return self._is_listening and not self._is_paused

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def load_model(self) -> None:
        """Loads the local Vosk acoustic model and configures the constrained phrase grammar."""
        if vosk is None:
            raise RuntimeError("vosk package is not installed. Please install vosk.")

        model_path = Path(self.config.model_dir)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Wake-word model directory not found at {model_path}.\n"
                f"Please ensure the local model 'vosk-model-small-en-us-0.15' is provisioned in models/wake_word/."
            )

        with self._lock:
            # Silence Vosk internal debug logging
            vosk.SetLogLevel(-1)
            logger.info("Loading local wake-word model from %s...", model_path)
            self._model = vosk.Model(str(model_path))

            # Grammar constraint: only recognize configured phrase or unknown speech ([unk])
            # This makes detection fast and eliminates vocabulary hallucinations
            clean_phrase = self.config.phrase.strip().lower()
            grammar = json.dumps([clean_phrase, "[unk]"])
            self._recognizer = vosk.KaldiRecognizer(self._model, self.config.sample_rate, grammar)
            self._recognizer.SetWords(False)
            self._is_loaded = True
            logger.info("Wake-word detector loaded successfully with phrase '%s'.", clean_phrase)

    def process_audio_chunk(self, pcm_bytes: bytes) -> bool:
        """
        Processes a raw 16-bit PCM mono audio chunk (for live stream or deterministic test mocks).
        Returns True if the activation phrase was detected.
        """
        if not self._is_loaded or self._recognizer is None or self._is_paused:
            return False

        now = time.time()
        if now - self._last_trigger_time < self.config.cooldown_seconds:
            return False

        # Stage 1: RMS energy gating to avoid running Kaldi on ambient room silence
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if len(samples) > 0:
                rms = float(np.sqrt(np.mean(samples ** 2)))
                if rms < self.config.energy_threshold:
                    return False
        except Exception:
            pass

        # Stage 2: Vosk acoustic phrase decoding
        detected = False
        target_phrase = self.config.phrase.strip().lower()

        with self._lock:
            if self._recognizer.AcceptWaveform(pcm_bytes):
                res_str = self._recognizer.Result()
                try:
                    res = json.loads(res_str)
                    text = res.get("text", "").lower().strip()
                    if target_phrase in text:
                        detected = True
                except Exception as e:
                    logger.debug("Failed parsing Vosk result: %s", e)
            else:
                part_str = self._recognizer.PartialResult()
                try:
                    part = json.loads(part_str)
                    partial_text = part.get("partial", "").lower().strip()
                    if target_phrase in partial_text:
                        detected = True
                except Exception as e:
                    logger.debug("Failed parsing Vosk partial result: %s", e)

            if detected:
                self._last_trigger_time = now
                self._recognizer.Reset()
                logger.info("Wake-word '%s' detected successfully!", target_phrase)
                return True

        return False

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """SoundDevice input stream callback executed on audio worker thread."""
        if status:
            logger.debug("Wake-word audio stream status: %s", status)

        if self._is_paused or not self._is_listening:
            return

        pcm_bytes = bytes(indata)
        if self.process_audio_chunk(pcm_bytes):
            if self._on_detected_callback:
                try:
                    self._on_detected_callback()
                except Exception as e:
                    logger.error("Error in wake-word detection callback: %s", e)

    def start(
        self,
        on_detected: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Starts background microphone stream for wake-word monitoring."""
        if not self.config.enabled:
            logger.info("Wake-word detector is disabled in configuration.")
            return

        if not self._is_loaded:
            self.load_model()

        if sd is None:
            err_msg = "sounddevice package is not installed; cannot capture microphone audio."
            logger.error(err_msg)
            if on_error:
                on_error(err_msg)
            return

        self._on_detected_callback = on_detected
        self._on_error_callback = on_error

        with self._lock:
            if self._stream is not None and self._stream.active:
                logger.info("Wake-word stream already active.")
                return

            try:
                self._stream = sd.RawInputStream(
                    samplerate=self.config.sample_rate,
                    blocksize=self.config.block_size,
                    device=self.config.input_device_index,
                    dtype="int16",
                    channels=1,
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._is_listening = True
                self._is_paused = False
                logger.info(
                    "Background wake-word stream started (device=%s, phrase='%s').",
                    self.config.input_device_index,
                    self.config.phrase,
                )
            except Exception as e:
                self._is_listening = False
                err_msg = f"Failed to open microphone stream for wake-word: {e}"
                logger.error(err_msg)
                if self._on_error_callback:
                    self._on_error_callback(err_msg)

    def pause(self) -> None:
        """Temporarily suspends detection (e.g. while user is actively recording or TTS is speaking)."""
        with self._lock:
            self._is_paused = True
            if self._recognizer is not None:
                try:
                    self._recognizer.Reset()
                except Exception:
                    pass
        logger.debug("Wake-word monitoring paused.")

    def resume(self) -> None:
        """Resumes background detection and clears lingering recognizer state."""
        with self._lock:
            if self._recognizer is not None:
                try:
                    self._recognizer.Reset()
                except Exception:
                    pass
            self._last_trigger_time = time.time()
            self._is_paused = False
        logger.debug("Wake-word monitoring resumed.")

    def stop(self) -> None:
        """Stops the audio stream and completely releases microphone hardware."""
        with self._lock:
            self._is_listening = False
            self._is_paused = False
            if self._stream is not None:
                try:
                    if self._stream.active:
                        self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.debug("Error stopping wake-word stream: %s", e)
                finally:
                    self._stream = None
        logger.info("Wake-word stream stopped and microphone released.")

    def unload(self) -> None:
        """Releases the model and closes active streams."""
        self.stop()
        with self._lock:
            self._recognizer = None
            self._model = None
            self._is_loaded = False
        logger.info("Wake-word detector unloaded.")
