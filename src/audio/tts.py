"""
Local Text-to-Speech (TTS) Engine using Piper.
Synthesizes speech locally on CPU, chunks long responses, strips diagnostic blocks,
and handles language boundaries safely.
"""

import logging
import re
import time
from pathlib import Path
from typing import NamedTuple
import numpy as np

try:
    import piper
except ImportError:
    piper = None

from src.audio.config import AudioConfig

logger = logging.getLogger("assistant.audio.tts")


class SynthesisResult(NamedTuple):
    audio_data: np.ndarray | None
    sample_rate: int
    synthesis_time_seconds: float
    audio_duration_seconds: float
    real_time_factor: float
    language_supported: bool
    text_spoken: str


class PiperTtsEngine:
    """Offline, CPU-only Piper TTS engine."""

    def __init__(self, config: AudioConfig):
        self.config = config
        self._voice = None
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_voice(self) -> None:
        """Loads the local Piper ONNX model into memory."""
        if piper is None:
            raise RuntimeError("piper-tts package is not installed.")

        model_path = Path(self.config.tts_model_path)
        config_path = Path(self.config.tts_config_path)

        if not model_path.exists():
            raise FileNotFoundError(
                f"TTS model not found at {model_path}.\n"
                f"Please run 'python scripts/download_assets.py --tts' to provision voice assets."
            )

        if not config_path.exists():
            raise FileNotFoundError(
                f"TTS config JSON not found at {config_path}.\n"
                f"Please run 'python scripts/download_assets.py --tts' to provision voice assets."
            )

        logger.info("Loading Piper voice model from %s (CPU mode)", model_path.name)
        start_time = time.time()
        self._voice = piper.PiperVoice.load(
            model_path=str(model_path),
            config_path=str(config_path),
            use_cuda=False,  # Strict CPU execution
        )
        self._is_loaded = True
        logger.info("Piper voice model loaded in %.2fs", time.time() - start_time)

    def unload_voice(self) -> None:
        """Releases the voice model from memory."""
        self._voice = None
        self._is_loaded = False
        logger.info("Piper voice model unloaded.")

    @staticmethod
    def is_persian_text(text: str) -> bool:
        """Detects whether text contains Persian/Arabic characters."""
        persian_chars = len(re.findall(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]", text))
        latin_chars = len(re.findall(r"[a-zA-Z]", text))
        return persian_chars > 0 and persian_chars >= latin_chars

    @staticmethod
    def sanitize_for_speech(text: str) -> str:
        """
        Strips markdown code blocks, JSON tool traces, URLs, and formatting
        so the assistant doesn't speak technical markup or brackets.
        """
        # Remove tool output sections
        text = re.sub(r"\[Tool Output \([^)]+\)\]:[^\n]*", "", text)
        text = re.sub(r"\[POLICY BLOCK\][^\n]*", "", text)

        # Remove fenced code blocks
        text = re.sub(r"```[\s\S]*?```", "", text)

        # Remove inline code backticks
        text = re.sub(r"`[^`]*`", "", text)

        # Remove markdown URLs: [label](url) -> label
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Remove markdown symbols (*, _, #, >, ~)
        text = re.sub(r"[*_#~>]", "", text)

        # Clean excess whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def synthesize(self, text: str) -> SynthesisResult:
        """
        Synthesizes speech from input text.
        Returns audio buffer, sample rate, and timing metadata.
        """
        clean_text = self.sanitize_for_speech(text)

        if not clean_text:
            return SynthesisResult(
                audio_data=None,
                sample_rate=self.config.tts_sample_rate,
                synthesis_time_seconds=0.0,
                audio_duration_seconds=0.0,
                real_time_factor=0.0,
                language_supported=True,
                text_spoken="",
            )

        # Honest language handling: English voice cannot synthesize Persian phonemes
        if self.is_persian_text(clean_text):
            logger.info("Text detected as Persian. Skipping English TTS synthesis to avoid corrupt phonemes.")
            return SynthesisResult(
                audio_data=None,
                sample_rate=self.config.tts_sample_rate,
                synthesis_time_seconds=0.0,
                audio_duration_seconds=0.0,
                real_time_factor=0.0,
                language_supported=False,
                text_spoken=clean_text,
            )

        if not self._is_loaded:
            self.load_voice()

        start_time = time.time()
        audio_chunks = []

        try:
            syn_config = piper.SynthesisConfig()
            if hasattr(self.config, "tts_speed") and self.config.tts_speed != 1.0:
                syn_config.length_scale = 1.0 / self.config.tts_speed

            for chunk in self._voice.synthesize(clean_text, syn_config=syn_config):
                if chunk.audio_float_array is not None:
                    audio_chunks.append(chunk.audio_float_array)

            synth_duration = time.time() - start_time

            if not audio_chunks:
                return SynthesisResult(
                    audio_data=None,
                    sample_rate=self.config.tts_sample_rate,
                    synthesis_time_seconds=synth_duration,
                    audio_duration_seconds=0.0,
                    real_time_factor=0.0,
                    language_supported=True,
                    text_spoken=clean_text,
                )

            full_audio = np.concatenate(audio_chunks)
            sr = self._voice.config.sample_rate if hasattr(self._voice, "config") else self.config.tts_sample_rate
            audio_duration = len(full_audio) / sr
            rtf = synth_duration / audio_duration if audio_duration > 0 else 0.0

            logger.info(
                "Synthesized %d samples (%.2fs audio) in %.2fs (RTF: %.2f)",
                len(full_audio),
                audio_duration,
                synth_duration,
                rtf,
            )

            return SynthesisResult(
                audio_data=full_audio,
                sample_rate=sr,
                synthesis_time_seconds=synth_duration,
                audio_duration_seconds=audio_duration,
                real_time_factor=rtf,
                language_supported=True,
                text_spoken=clean_text,
            )

        except Exception as e:
            logger.error("TTS synthesis error: %s", e)
            return SynthesisResult(
                audio_data=None,
                sample_rate=self.config.tts_sample_rate,
                synthesis_time_seconds=time.time() - start_time,
                audio_duration_seconds=0.0,
                real_time_factor=0.0,
                language_supported=True,
                text_spoken=clean_text,
            )
