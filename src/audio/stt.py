"""
Local Speech-to-Text (STT) Engine using faster-whisper.
Runs strictly on CPU with INT8 quantization, enforces local-only files,
and provides detailed timing metadata and language detection.
"""

import logging
import threading
import time
from pathlib import Path
from typing import NamedTuple
import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

from src.audio.config import AudioConfig

logger = logging.getLogger("assistant.audio.stt")


class TranscriptionResult(NamedTuple):
    text: str
    language: str
    language_probability: float
    duration_seconds: float
    transcription_time_seconds: float
    real_time_factor: float
    is_empty: bool


class WhisperSttEngine:
    """Offline, CPU-only faster-whisper STT engine."""

    def __init__(self, config: AudioConfig):
        self.config = config
        self._model = None
        self._is_loaded = False
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> None:
        """Loads the local CTranslate2 INT8 model into memory."""
        if WhisperModel is None:
            raise RuntimeError("faster-whisper package is not installed.")

        model_dir = Path(self.config.stt_model_dir)
        if not model_dir.exists() or not (model_dir / "model.bin").exists():
            raise FileNotFoundError(
                f"STT model files not found in {model_dir}.\n"
                f"Please run 'python scripts/download_assets.py --stt' to provision the model."
            )

        with self._lock:
            logger.info("Loading Whisper model from %s (CPU INT8, %d threads)", model_dir.name, self.config.stt_threads)
            start_time = time.time()
            self._model = WhisperModel(
                model_size_or_path=str(model_dir),
                device="cpu",
                compute_type="int8",
                cpu_threads=self.config.stt_threads,
                num_workers=1,
                local_files_only=True,  # Guarantee offline integrity
            )
            self._is_loaded = True
            logger.info("Whisper model loaded in %.2fs", time.time() - start_time)

    def unload_model(self) -> None:
        """Releases the Whisper model from memory."""
        with self._lock:
            self._model = None
            self._is_loaded = False
            logger.info("Whisper model unloaded.")

    def transcribe(
        self,
        audio: np.ndarray | str | Path,
        language: str | None = None,
    ) -> TranscriptionResult:
        """
        Transcribes audio (in-memory float32 16kHz mono array or audio file path).
        Enforces single-threaded job execution via concurrency lock.
        """
        if not self._is_loaded:
            self.load_model()

        # Handle empty or zero-length audio buffers
        if isinstance(audio, np.ndarray):
            if len(audio) == 0:
                return TranscriptionResult(
                    text="",
                    language="unknown",
                    language_probability=0.0,
                    duration_seconds=0.0,
                    transcription_time_seconds=0.0,
                    real_time_factor=0.0,
                    is_empty=True,
                )
            # Energy/silence check
            rms = float(np.sqrt(np.mean(audio**2)))
            if rms < 0.0005:
                return TranscriptionResult(
                    text="",
                    language="silence",
                    language_probability=1.0,
                    duration_seconds=len(audio) / self.config.stt_sample_rate,
                    transcription_time_seconds=0.0,
                    real_time_factor=0.0,
                    is_empty=True,
                )

            # Peak normalization to ensure clear signal across long multi-clause utterances
            if getattr(self.config, "stt_normalize_audio", True):
                peak = float(np.max(np.abs(audio)))
                if peak > 0.005:
                    audio = (audio / peak) * 0.95

        target_lang = language if language is not None else self.config.stt_language
        if isinstance(target_lang, str) and target_lang.lower() in ("auto", "none", ""):
            target_lang = None

        # Bias Persian vocabulary and orthography if target language is 'fa'
        initial_prompt = (
            getattr(self.config, "stt_initial_prompt", None)
            if target_lang == "fa"
            else None
        )

        with self._lock:
            start_time = time.time()
            try:
                vad_filter = getattr(self.config, "stt_vad_filter", True)
                vad_params = (
                    dict(
                        threshold=getattr(self.config, "stt_vad_threshold", 0.25),
                        min_silence_duration_ms=getattr(self.config, "stt_vad_min_silence_ms", 1500),
                        speech_pad_ms=getattr(self.config, "stt_vad_speech_pad_ms", 400),
                    )
                    if vad_filter
                    else None
                )

                segments, info = self._model.transcribe(
                    audio,
                    beam_size=5,
                    language=target_lang,
                    task="transcribe",
                    vad_filter=vad_filter,
                    vad_parameters=vad_params,
                    condition_on_previous_text=getattr(self.config, "stt_condition_on_previous_text", False),
                    initial_prompt=initial_prompt,
                    no_speech_threshold=0.6,
                )

                collected_text = " ".join([seg.text.strip() for seg in segments if seg.text.strip()]).strip()
                transcribe_duration = time.time() - start_time
                audio_duration = info.duration if hasattr(info, "duration") else 0.0
                rtf = transcribe_duration / audio_duration if audio_duration > 0 else 0.0

                is_empty = len(collected_text) == 0

                logger.info(
                    "Transcribed %.2fs audio in %.2fs (RTF: %.2f) -> '%s' (Lang: %s, Prob: %.2f)",
                    audio_duration,
                    transcribe_duration,
                    rtf,
                    collected_text,
                    info.language,
                    info.language_probability,
                )

                return TranscriptionResult(
                    text=collected_text,
                    language=info.language,
                    language_probability=round(info.language_probability, 3),
                    duration_seconds=round(audio_duration, 2),
                    transcription_time_seconds=round(transcribe_duration, 3),
                    real_time_factor=round(rtf, 3),
                    is_empty=is_empty,
                )

            except Exception as e:
                logger.error("STT transcription error: %s", e)
                return TranscriptionResult(
                    text="",
                    language="error",
                    language_probability=0.0,
                    duration_seconds=0.0,
                    transcription_time_seconds=time.time() - start_time,
                    real_time_factor=0.0,
                    is_empty=True,
                )
