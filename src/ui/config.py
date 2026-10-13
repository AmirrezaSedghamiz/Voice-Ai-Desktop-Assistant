"""
UI and Application Configuration:
Manages persistent user settings (audio devices, wake-word toggles, tray behavior)
stored locally in data/ui_settings.json.
"""

import json
import logging
import sys
from pathlib import Path
from pydantic import BaseModel, Field

logger = logging.getLogger("assistant.ui.config")

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "data" / "ui_settings.json"


class UiConfig(BaseModel):
    """Persistent user preferences for the desktop assistant."""

    # Identity
    assistant_name: str = Field(default="David", description="Display name of the assistant.")

    # Wake-word settings
    wake_word_enabled: bool = Field(default=True, description="Enable local wake-word background listening.")
    wake_phrase: str = Field(default="activate david", description="Configured activation phrase.")
    wake_energy_threshold: float = Field(
        default=0.010,
        ge=0.001,
        le=0.2,
        description="RMS energy threshold before triggering acoustic keyword detector.",
    )

    # Audio device & trigger settings
    input_device_index: int | None = Field(default=None, description="Selected microphone device index.")
    output_device_index: int | None = Field(default=None, description="Selected speaker device index.")
    tts_enabled: bool = Field(default=True, description="Enable spoken voice responses.")
    trigger_mode: str = Field(default="vad", description="Voice interaction mode: 'vad' or 'ptt'.")

    # Desktop window behavior
    minimize_to_tray_on_close: bool = Field(
        default=True,
        description="Minimizes to Windows system tray instead of exiting when clicking window close button.",
    )
    start_minimized: bool = Field(default=False, description="Start minimized to the system tray.")
    dark_mode: bool = Field(default=True, description="Use professional dark theme palette.")

    @classmethod
    def load(cls, file_path: Path = DEFAULT_SETTINGS_PATH) -> "UiConfig":
        """Loads configuration from JSON file or returns defaults if absent."""
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception as e:
                logger.warning("Could not load UI settings from %s, using defaults: %s", file_path, e)
        return cls()

    def save(self, file_path: Path = DEFAULT_SETTINGS_PATH) -> None:
        """Persists settings safely to JSON file."""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = self.model_dump_json(indent=2)
            file_path.write_text(content, encoding="utf-8")
            logger.info("Saved UI settings to %s", file_path)
        except Exception as e:
            logger.error("Failed to save UI settings to %s: %s", file_path, e)
