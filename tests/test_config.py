"""
Tests for configuration validation and security boundaries.
"""

import pytest
from pydantic import ValidationError
from src.core.config import AssistantSettings, NetworkIsolationConfig, get_default_settings


def test_default_settings():
    settings = get_default_settings()
    assert settings.governor.cpu_threads == 4
    assert settings.governor.gpu_layers == 24
    assert settings.governor.max_context_tokens == 2048
    assert settings.governor.max_concurrent_requests == 1
    assert settings.network.server_host == "127.0.0.1"
    assert settings.network.server_port == 8080
    assert settings.network.allow_external_networking is False


def test_low_resource_preset():
    settings = get_default_settings(low_resource=True)
    assert settings.governor.low_resource_mode is True
    assert settings.governor.cpu_threads == 2
    assert settings.governor.gpu_layers == 12
    assert settings.governor.max_context_tokens == 1024
    assert settings.governor.process_priority == "IDLE"


def test_loopback_security_enforcement():
    # Valid loopbacks
    cfg1 = NetworkIsolationConfig(server_host="127.0.0.1")
    assert cfg1.server_host == "127.0.0.1"

    cfg2 = NetworkIsolationConfig(server_host="localhost")
    assert cfg2.server_host == "localhost"

    # Non-loopback must be rejected by Pydantic validator
    with pytest.raises(ValidationError):
        NetworkIsolationConfig(server_host="192.168.1.50")

    with pytest.raises(ValidationError):
        NetworkIsolationConfig(server_host="api.openai.com")


def test_prohibit_external_networking():
    with pytest.raises(ValidationError):
        NetworkIsolationConfig(allow_external_networking=True)
