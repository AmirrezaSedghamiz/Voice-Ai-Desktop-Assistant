"""
Configuration schemas for the audio subsystem (STT, TTS, devices, and triggers).
"""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class AudioConfig(BaseModel):
    """Configuration settings for audio input, output, STT, and TTS."""

    # STT Settings
    stt_enabled: bool = Field(default=True, description="Enable local speech-to-text input.")
    stt_model_dir: Path = Field(
        default=PROJECT_ROOT / "models" / "stt" / "whisper-base",
        description="Path to local quantized Whisper model directory.",
    )
    stt_sample_rate: int = Field(default=16000, description="Audio capture sampling rate (Hz) for STT.")
    stt_threads: int = Field(default=4, ge=1, le=8, description="CPU threads for Whisper transcription.")
    stt_language: str | None = Field(
        default="fa",
        description="Language code (e.g., 'fa', 'en') or None/'auto' for auto-detect. Defaults to Persian ('fa').",
    )
    stt_initial_prompt: str | None = Field(
        default="سلام، دستیار صوتی ویندوز.",
        description="Initial prompt context to bias Persian vocabulary and orthography.",
    )
    stt_vad_filter: bool = Field(default=True, description="Enable VAD pre-filtering in faster-whisper.")
    stt_vad_threshold: float = Field(default=0.25, ge=0.05, le=0.9, description="Speech onset threshold (lower preserves quieter clauses).")
    stt_vad_min_silence_ms: int = Field(default=1500, ge=300, le=5000, description="Silence duration before splitting speech chunks in STT.")
    stt_vad_speech_pad_ms: int = Field(default=400, ge=100, le=1000, description="Padding on speech boundaries to avoid clipping words.")
    stt_condition_on_previous_text: bool = Field(
        default=False,
        description="Disabled by default to prevent hallucination cascades and dropped sentences in long speech.",
    )
    stt_normalize_audio: bool = Field(
        default=True,
        description="Peak normalize audio buffer before transcription for consistent volume and SNR.",
    )

    # TTS Settings
    tts_enabled: bool = Field(default=True, description="Enable local text-to-speech output.")
    tts_model_path: Path = Field(
        default=PROJECT_ROOT / "models" / "tts" / "en_US-lessac-medium.onnx",
        description="Path to local Piper ONNX voice model.",
    )
    tts_config_path: Path = Field(
        default=PROJECT_ROOT / "models" / "tts" / "en_US-lessac-medium.onnx.json",
        description="Path to local Piper ONNX voice JSON configuration.",
    )
    tts_sample_rate: int = Field(default=22050, description="Playback sampling rate for Piper.")
    tts_speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech rate (1.0 = normal).")

    # Audio Device & Trigger Settings
    input_device_index: int | None = Field(default=None, description="Audio input device index (None = system default).")
    output_device_index: int | None = Field(default=None, description="Audio output device index (None = system default).")
    trigger_mode: Literal["ptt", "vad"] = Field(
        default="ptt",
        description="Voice trigger mode: 'ptt' (Push-to-Talk) or 'vad' (Voice Activity Detection).",
    )
    max_recording_seconds: int = Field(default=120, ge=1, le=300, description="Maximum recording duration in seconds (2 minutes).")
    vad_silence_duration_ms: int = Field(default=1800, ge=500, le=5000, description="Silence duration to end utterance in VAD mode (1.8s).")
    vad_energy_threshold: float = Field(default=0.015, ge=0.001, le=0.5, description="RMS energy threshold for speech onset.")
