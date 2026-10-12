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
    stt_language: str | None = Field(default=None, description="Language code (e.g., 'en', 'fa') or None for auto-detect.")

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
    max_recording_seconds: int = Field(default=30, ge=3, le=120, description="Maximum recording duration in seconds.")
    vad_silence_duration_ms: int = Field(default=800, ge=300, le=3000, description="Silence duration to end utterance in VAD mode.")
    vad_energy_threshold: float = Field(default=0.015, ge=0.001, le=0.5, description="RMS energy threshold for speech onset.")
