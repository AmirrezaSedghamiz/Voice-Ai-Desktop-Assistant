"""
Deterministic Synthetic Audio Waveform & PCM Chunk Generator.
Generates in-memory audio buffers for offline STT and Wake-Word testing without relying on physical hardware.
"""

from __future__ import annotations

import numpy as np


def generate_silence(duration_seconds: float = 1.0, sample_rate: int = 16000) -> np.ndarray:
    """Generates zero-energy silence float32 array in [-1.0, 1.0]."""
    num_samples = int(duration_seconds * sample_rate)
    return np.zeros(num_samples, dtype=np.float32)


def generate_noise(
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
    amplitude: float = 0.05,
    seed: int = 42,
) -> np.ndarray:
    """Generates reproducible Gaussian white noise."""
    rng = np.random.RandomState(seed)
    num_samples = int(duration_seconds * sample_rate)
    noise = rng.normal(0, amplitude, num_samples).astype(np.float32)
    return np.clip(noise, -1.0, 1.0)


def generate_sine_wave(
    frequency: float = 440.0,
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> np.ndarray:
    """Generates a pure sinusoidal tone."""
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    wave = amplitude * np.sin(2 * np.pi * frequency * t).astype(np.float32)
    return wave


def float32_to_pcm16_bytes(audio: np.ndarray) -> bytes:
    """Converts normalized float32 array [-1.0, 1.0] to 16-bit signed PCM bytes."""
    scaled = np.clip(audio * 32767.0, -32768.0, 32767.0).astype(np.int16)
    return scaled.tobytes()
