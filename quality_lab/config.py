"""
Quality Lab Configuration & Release Policies.
Controls execution limits, asset directories, hardware opt-in flags,
evaluation thresholds, and release-gating criteria.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent


class QualityLabConfig(BaseModel):
    """Configuration for Quality Lab execution runs and evaluations."""

    project_root: Path = Field(default=PROJECT_ROOT)
    reports_dir: Path = Field(default=PROJECT_ROOT / "data" / "quality_lab" / "reports")
    baselines_dir: Path = Field(default=PROJECT_ROOT / "quality_lab" / "baselines")
    datasets_dir: Path = Field(default=PROJECT_ROOT / "quality_lab" / "datasets")
    temp_sandbox_dir: Path = Field(default=PROJECT_ROOT / "data" / "quality_lab" / "sandbox")

    # Execution controls
    allow_hardware: bool = Field(
        default=False,
        description="Whether to execute live microphone/audio device and physical GPU tests.",
    )
    allow_heavy_models: bool = Field(
        default=False,
        description="Whether to spin up the full 1.7B LLM or larger models during test runs.",
    )
    exe_path: Optional[Path] = Field(
        default=PROJECT_ROOT / "dist" / "david_assistant" / "david_assistant.exe",
        description="Path to the packaged Windows executable to validate.",
    )
    timeout_seconds: float = Field(default=45.0, ge=5.0, le=300.0)

    # Release gate quality and performance thresholds
    min_ai_accuracy_percent: float = Field(default=90.0, description="Minimum acceptable AI evaluation pass percentage")
    min_intent_accuracy_percent: float = Field(default=95.0, description="Minimum semantic intent extraction accuracy")
    max_wer_threshold: float = Field(default=0.25, description="Maximum allowable Word Error Rate on clean speech")
    max_cer_threshold: float = Field(default=0.15, description="Maximum allowable Character Error Rate on Persian speech")
    max_ttft_seconds: float = Field(default=2.0, description="Max acceptable Time-To-First-Token in seconds")
    min_tokens_per_second: float = Field(default=15.0, description="Min acceptable generation throughput in tokens/sec")
    max_peak_ram_gb: float = Field(default=6.0, description="Max allowable resident memory in GB")
    max_peak_vram_mb: float = Field(default=3500.0, description="Max allowable VRAM offload in MB")
    max_wake_word_latency_seconds: float = Field(default=0.75, description="Max acceptable keyword spotter detection latency")

    # Privacy & Safety guarantees
    strict_offline: bool = Field(default=True, description="Enforce zero external network queries during execution")
    redact_sensitive_content: bool = Field(default=True, description="Filter user identifiers and tokens from test reports")


def get_default_lab_config() -> QualityLabConfig:
    cfg = QualityLabConfig()
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    cfg.temp_sandbox_dir.mkdir(parents=True, exist_ok=True)
    return cfg
