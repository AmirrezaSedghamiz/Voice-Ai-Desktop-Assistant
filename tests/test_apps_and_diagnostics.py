"""
Unit tests for App Launcher and System Diagnostics handlers.
"""

import pytest
from src.agent.tools.handlers.apps import (
    launch_application,
    resolve_app_name,
)
from src.agent.tools.handlers.diagnostics import (
    diagnostic_echo,
    get_battery_status,
    get_network_adapter_status,
    get_resource_metrics,
    get_system_status,
    ping_host,
)


def test_app_launcher_name_resolution():
    # English names & aliases
    assert resolve_app_name("notepad") == "notepad"
    assert resolve_app_name("Notepad") == "notepad"
    assert resolve_app_name("calc") == "calculator"
    assert resolve_app_name("calculator") == "calculator"
    assert resolve_app_name("paint") == "paint"
    assert resolve_app_name("file explorer") == "explorer"
    assert resolve_app_name("task manager") == "taskmgr"

    # Persian aliases
    assert resolve_app_name("یادداشت") == "notepad"
    assert resolve_app_name("نوت پد") == "notepad"
    assert resolve_app_name("ماشین حساب") == "calculator"
    assert resolve_app_name("نقاشی") == "paint"
    assert resolve_app_name("تسک منیجر") == "taskmgr"
    assert resolve_app_name("اکسپلورر") == "explorer"

    # Disallowed apps
    assert resolve_app_name("cmd") is None
    assert resolve_app_name("powershell") is None
    assert resolve_app_name("regedit") is None
    assert resolve_app_name("format.com") is None


def test_app_launcher_execution_mock():
    # Launch allowed app
    res = launch_application("notepad", mock_for_test=True)
    assert res.success is True
    assert res.result["launched"] == "notepad"
    assert res.result["executable"] == "notepad.exe"

    # Persian launch
    res_fa = launch_application("ماشین حساب", mock_for_test=True)
    assert res_fa.success is True
    assert res_fa.result["launched"] == "calculator"
    assert res_fa.result["executable"] == "calc.exe"

    # Launch forbidden app rejected
    res_bad = launch_application("cmd.exe", mock_for_test=True)
    assert res_bad.success is False
    assert "not in the approved allowlist" in res_bad.error


def test_ping_host_validation_and_execution():
    # Dangerous injection attempts must be blocked immediately
    bad1 = ping_host("127.0.0.1; whoami")
    assert bad1.success is False
    assert "Security Violation" in bad1.error

    bad2 = ping_host("localhost && calc")
    assert bad2.success is False

    bad3 = ping_host("| dir")
    assert bad3.success is False

    # Valid loopback ping
    valid_res = ping_host("127.0.0.1", count=1)
    assert valid_res.success is True
    assert valid_res.result["host"] == "127.0.0.1"
    assert valid_res.result["reachable"] is True


def test_system_diagnostics():
    # Battery status
    batt = get_battery_status()
    assert batt.success is True
    assert "percent" in batt.result
    assert "power_plugged" in batt.result

    # System status
    sys_stat = get_system_status()
    assert sys_stat.success is True
    assert sys_stat.result["status"] == "healthy"
    assert sys_stat.result["cpu_count"] > 0
    assert sys_stat.result["ram_total_gb"] > 0

    # Resource metrics
    metrics = get_resource_metrics()
    assert metrics.success is True
    assert "cpu_percent" in metrics.result
    assert "virtual_memory_percent" in metrics.result
    assert "disk_percent" in metrics.result

    # Network adapters
    net = get_network_adapter_status()
    assert net.success is True
    assert isinstance(net.result["adapters"], list)

    # Echo
    echo = diagnostic_echo("Testing 123")
    assert echo.success is True
    assert echo.result["echo"] == "Testing 123"
