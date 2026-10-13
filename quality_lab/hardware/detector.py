"""
Hardware and Local Neural Model Environment Detector.
Passively queries the Windows host to detect CPU, RAM, NVIDIA GPU/VRAM,
audio hardware (microphones/speakers), and local neural model presence without modifying system state.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Optional
import psutil
from pydantic import BaseModel, Field

try:
    import sounddevice as sd
except ImportError:
    sd = None


class ModelAvailability(BaseModel):
    """Presence and size of local, offline model weights and binaries."""

    llm_present: bool = False
    llm_path: Optional[str] = None
    llm_size_bytes: int = 0

    stt_present: bool = False
    stt_path: Optional[str] = None

    tts_present: bool = False
    tts_path: Optional[str] = None

    wake_word_present: bool = False
    wake_word_path: Optional[str] = None

    llama_server_present: bool = False
    llama_server_path: Optional[str] = None

    @property
    def all_models_present(self) -> bool:
        return (
            self.llm_present
            and self.stt_present
            and self.tts_present
            and self.wake_word_present
            and self.llama_server_present
        )


class HardwareCapabilities(BaseModel):
    """Host Windows system capabilities and hardware inventory."""

    os_system: str = Field(default_factory=platform.system)
    os_release: str = Field(default_factory=platform.release)
    os_version: str = Field(default_factory=platform.version)
    architecture: str = Field(default_factory=lambda: platform.machine())

    cpu_count_physical: int = Field(default_factory=lambda: psutil.cpu_count(logical=False) or 1)
    cpu_count_logical: int = Field(default_factory=lambda: psutil.cpu_count(logical=True) or 1)
    total_ram_gb: float = 0.0
    available_ram_gb: float = 0.0

    gpu_available: bool = False
    gpu_name: Optional[str] = None
    gpu_vram_total_mb: Optional[float] = None
    gpu_driver_version: Optional[str] = None

    audio_input_available: bool = False
    audio_output_available: bool = False
    input_device_count: int = 0
    output_device_count: int = 0

    models: ModelAvailability = Field(default_factory=ModelAvailability)

    def can_run_live_voice(self) -> bool:
        return self.audio_input_available and self.audio_output_available

    def can_run_live_inference(self) -> bool:
        return self.models.llm_present and self.models.llama_server_present


def detect_hardware_capabilities(project_root: Path) -> HardwareCapabilities:
    """Inspects the local Windows environment and returns detected capabilities."""
    mem = psutil.virtual_memory()
    total_ram = round(mem.total / (1024**3), 2)
    avail_ram = round(mem.available / (1024**3), 2)

    # Detect NVIDIA GPU via nvidia-smi if present
    gpu_available = False
    gpu_name = None
    gpu_vram_mb = None
    gpu_driver = None

    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            text=True,
            timeout=3,
            creationflags=flags,
        ).strip()
        if out:
            lines = out.split("\n")
            if lines:
                parts = lines[0].split(",")
                if len(parts) >= 3:
                    gpu_name = parts[0].strip()
                    gpu_vram_mb = float(parts[1].strip())
                    gpu_driver = parts[2].strip()
                    gpu_available = True
    except Exception:
        pass

    # Detect audio devices via sounddevice
    input_count = 0
    output_count = 0
    if sd is not None:
        try:
            devices = sd.query_devices()
            for d in devices:
                if d.get("max_input_channels", 0) > 0:
                    input_count += 1
                if d.get("max_output_channels", 0) > 0:
                    output_count += 1
        except Exception:
            pass

    # Inspect model presence
    models_dir = project_root / "models"
    llm_file = models_dir / "Qwen3-1.7B-Q4_K_M.gguf"
    stt_dir = models_dir / "stt" / "whisper-base"
    tts_file = models_dir / "tts" / "en_US-lessac-medium.onnx"
    wake_dir = models_dir / "wake_word" / "vosk-model-small-en-us-0.15"
    llama_exe = project_root / "bin" / "llama.cpp" / "llama-server.exe"

    models_info = ModelAvailability(
        llm_present=llm_file.exists(),
        llm_path=str(llm_file) if llm_file.exists() else None,
        llm_size_bytes=llm_file.stat().st_size if llm_file.exists() else 0,
        stt_present=(stt_dir / "model.bin").exists(),
        stt_path=str(stt_dir) if (stt_dir / "model.bin").exists() else None,
        tts_present=tts_file.exists(),
        tts_path=str(tts_file) if tts_file.exists() else None,
        wake_word_present=wake_dir.exists(),
        wake_word_path=str(wake_dir) if wake_dir.exists() else None,
        llama_server_present=llama_exe.exists(),
        llama_server_path=str(llama_exe) if llama_exe.exists() else None,
    )

    return HardwareCapabilities(
        total_ram_gb=total_ram,
        available_ram_gb=avail_ram,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        gpu_vram_total_mb=gpu_vram_mb,
        gpu_driver_version=gpu_driver,
        audio_input_available=(input_count > 0),
        audio_output_available=(output_count > 0),
        input_device_count=input_count,
        output_device_count=output_count,
        models=models_info,
    )
