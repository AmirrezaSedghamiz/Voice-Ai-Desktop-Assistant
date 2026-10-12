"""
Tests for Resource Governor priority and telemetry controls.
"""

import time
from src.core.config import ResourceGovernorConfig
from src.core.governor import ResourceGovernor


def test_system_telemetry_collection():
    config = ResourceGovernorConfig()
    governor = ResourceGovernor(config)
    telemetry = governor.get_system_telemetry()

    assert telemetry.cpu_percent >= 0.0
    assert telemetry.ram_total_gb > 0.0
    assert telemetry.ram_used_gb > 0.0
    assert telemetry.ram_percent > 0.0


def test_activity_touch():
    config = ResourceGovernorConfig(idle_timeout_seconds=30)
    governor = ResourceGovernor(config)
    t0 = governor.last_activity_time
    time.sleep(0.05)
    governor.touch_activity()
    assert governor.last_activity_time > t0
