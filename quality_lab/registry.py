"""
Quality Lab Suite Registry.
Central registry mapping suite names to their execution harnesses.
"""

from __future__ import annotations

from typing import Callable, Type
from quality_lab.config import QualityLabConfig
from quality_lab.suites.ai_eval_suite import AiEvalSuite
from quality_lab.suites.gui_suite import GuiSuite
from quality_lab.suites.integration_suite import IntegrationSuite
from quality_lab.suites.packaged_suite import PackagedSuite
from quality_lab.suites.performance_suite import PerformanceSuite
from quality_lab.suites.security_suite import SecuritySuite
from quality_lab.suites.tts_suite import TtsSuite
from quality_lab.suites.unit_suite import UnitSuite
from quality_lab.suites.voice_suite import VoiceSuite
from quality_lab.suites.wake_word_suite import WakeWordSuite


AVAILABLE_SUITES = {
    "unit": UnitSuite,
    "integration": IntegrationSuite,
    "ai": AiEvalSuite,
    "voice": VoiceSuite,
    "wake_word": WakeWordSuite,
    "tts": TtsSuite,
    "security": SecuritySuite,
    "performance": PerformanceSuite,
    "gui": GuiSuite,
    "packaged": PackagedSuite,
}


def get_suite_instance(name: str, config: QualityLabConfig) -> Any:
    """Returns an initialized suite instance by name."""
    cls = AVAILABLE_SUITES.get(name.lower())
    if not cls:
        raise KeyError(f"Unknown test suite '{name}'. Available suites: {list_available_suites()}")
    return cls(config)


def list_available_suites() -> list[str]:
    """Returns sorted list of available suite names."""
    return sorted(list(AVAILABLE_SUITES.keys()))
