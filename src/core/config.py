"""
Configuration schemas and settings for the Resource-Constrained Local AI Assistant.
Enforces strict offline boundaries, validated parameter limits, and resource budgeting.
"""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ResourceGovernorConfig(BaseModel):
    """Resource controls to ensure the assistant does not monopolize CPU/RAM/VRAM."""

    cpu_threads: int = Field(default=4, ge=1, le=16, description="Max CPU worker threads for inference.")
    process_priority: Literal["IDLE", "BELOW_NORMAL", "NORMAL"] = Field(
        default="BELOW_NORMAL",
        description="Windows process priority class for inference workers."
    )
    gpu_layers: int = Field(
        default=24,
        ge=0,
        le=40,
        description="Number of model layers offloaded to NVIDIA GPU (0 = CPU-only)."
    )
    max_context_tokens: int = Field(
        default=2048,
        ge=256,
        le=8192,
        description="Maximum context length in tokens."
    )
    max_output_tokens: int = Field(
        default=512,
        ge=16,
        le=2048,
        description="Maximum tokens generated per turn."
    )
    max_concurrent_requests: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Strict concurrency limit. 1 ensures no memory spikes."
    )
    idle_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Unload model from RAM/VRAM after inactivity."
    )
    low_resource_mode: bool = Field(
        default=False,
        description="Low resource preset (throttled threads, reduced context, lower GPU usage)."
    )


class NetworkIsolationConfig(BaseModel):
    """Strict offline boundary validation."""

    allow_external_networking: bool = Field(
        default=False,
        description="Must remain False. Enforces local-only loopback endpoints."
    )
    server_host: str = Field(
        default="127.0.0.1",
        description="Loopback host to bind inference server. Strictly local."
    )
    server_port: int = Field(
        default=8080,
        ge=1024,
        le=65535,
        description="Local port for inference server."
    )

    @field_validator("server_host")
    @classmethod
    def validate_loopback_only(cls, v: str) -> str:
        if v not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(f"Security Violation: server_host must be loopback. Got: {v}")
        return v

    @field_validator("allow_external_networking")
    @classmethod
    def validate_no_external(cls, v: bool) -> bool:
        if v:
            raise ValueError("Security Violation: External networking is prohibited.")
        return False


class MemoryConfig(BaseModel):
    """Configuration for persistent local SQLite memory store and profile injection budgets."""

    db_path: Path = Field(
        default=PROJECT_ROOT / "data" / "assistant_memory.db",
        description="Local SQLite database path for persistent facts and notes.",
    )
    max_profile_facts: int = Field(
        default=15,
        ge=1,
        le=100,
        description="Maximum number of active profile facts injected into the system prompt.",
    )
    max_profile_chars: int = Field(
        default=800,
        ge=100,
        le=4000,
        description="Maximum character budget for serialized profile facts in the system prompt.",
    )
    max_recall_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of FTS5 search results returned per recall query.",
    )
    max_query_length: int = Field(
        default=256,
        ge=8,
        le=1024,
        description="Maximum allowed character length for search queries.",
    )
    max_fact_key_chars: int = Field(
        default=100,
        ge=2,
        le=200,
        description="Maximum character length for a normalized fact key.",
    )
    max_fact_value_chars: int = Field(
        default=1000,
        ge=1,
        le=4000,
        description="Maximum character length for a stored fact value.",
    )
    max_note_title_chars: int = Field(
        default=200,
        ge=1,
        le=500,
        description="Maximum character length for a note title.",
    )
    max_note_content_chars: int = Field(
        default=10000,
        ge=1,
        le=50000,
        description="Maximum character length for note content.",
    )
    auto_extract_memories: bool = Field(
        default=False,
        description="Must remain False by default; only explicit or user-confirmed memories are stored.",
    )


class AssistantSettings(BaseModel):
    """Master application settings."""

    app_name: str = "Resource-Constrained Desktop AI Assistant"
    version: str = "0.3.0"
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    model_path: Path = PROJECT_ROOT / "models" / "Qwen3-1.7B-Q4_K_M.gguf"
    llama_bin_dir: Path = PROJECT_ROOT / "bin" / "llama.cpp"
    log_dir: Path = PROJECT_ROOT / "logs"
    governor: ResourceGovernorConfig = Field(default_factory=ResourceGovernorConfig)
    network: NetworkIsolationConfig = Field(default_factory=NetworkIsolationConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    def apply_low_resource_preset(self) -> None:
        """Applies conservative constraints for low-resource or battery operation."""
        self.governor.low_resource_mode = True
        self.governor.cpu_threads = 2
        self.governor.process_priority = "IDLE"
        self.governor.gpu_layers = 12
        self.governor.max_context_tokens = 1024
        self.governor.max_output_tokens = 256
        self.governor.idle_timeout_seconds = 120
        self.memory.max_profile_facts = 8
        self.memory.max_profile_chars = 400


def get_default_settings(low_resource: bool = False) -> AssistantSettings:
    """Factory creating validated assistant configuration."""
    settings = AssistantSettings()
    if low_resource:
        settings.apply_low_resource_preset()
    return settings

