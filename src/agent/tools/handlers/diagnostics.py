"""
Safe System Diagnostics Handler.
Provides read-only telemetry, bounded ping execution with strict host validation,
battery status, and network adapter queries.
Zero shell invocation (shell=False) and zero external API dependencies.
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any
import psutil

from src.agent.policy_engine import FORBIDDEN_CHAR_REGEX, HOST_REGEX
from src.agent.tools.models import ExecutionStatus, ToolResult

logger = logging.getLogger(__name__)


def ping_host(
    host: str,
    count: int = 2,
    timeout_seconds: float = 8.0,
    **kwargs: Any,
) -> ToolResult:
    """
    Executes a bounded ping against an approved hostname or IP address.
    Strictly validates input against command-injection characters and runs without shell.
    """
    if not host or not isinstance(host, str):
        return ToolResult.fail("Host parameter is required.")

    cleaned_host = host.strip()

    # Reject any dangerous shell metacharacters
    if FORBIDDEN_CHAR_REGEX.search(cleaned_host) or not HOST_REGEX.match(cleaned_host):
        return ToolResult.fail(
            f"Security Violation: Host '{cleaned_host}' contains invalid characters or format."
        )

    bounded_count = max(1, min(int(count), 4))

    try:
        cmd = ["ping.exe", "-n", str(bounded_count), cleaned_host]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
        stdout = proc.stdout

        # Parse Windows ping output
        # Packets: Sent = 2, Received = 2, Lost = 0 (0% loss)
        sent = bounded_count
        received = 0
        loss_pct = 100
        avg_ms = None

        m_packets = re.search(r"Sent = (\d+), Received = (\d+), Lost = (\d+)", stdout)
        if m_packets:
            sent = int(m_packets.group(1))
            received = int(m_packets.group(2))
            loss_pct = int(((sent - received) / sent) * 100) if sent > 0 else 100

        m_rtt = re.search(r"Average = (\d+)ms", stdout)
        if m_rtt:
            avg_ms = int(m_rtt.group(1))

        is_reachable = received > 0

        return ToolResult.ok(
            {
                "host": cleaned_host,
                "reachable": is_reachable,
                "packets_sent": sent,
                "packets_received": received,
                "packet_loss_percent": loss_pct,
                "avg_roundtrip_ms": avg_ms,
                "summary": (
                    f"Host '{cleaned_host}' is reachable with {avg_ms}ms latency."
                    if is_reachable
                    else f"Host '{cleaned_host}' was not reachable ({loss_pct}% packet loss)."
                ),
            }
        )
    except subprocess.TimeoutExpired:
        return ToolResult.fail(f"Ping request to '{cleaned_host}' timed out after {timeout_seconds}s.")
    except Exception as e:
        logger.error("Ping error for %s: %s", cleaned_host, e)
        return ToolResult.fail(f"Error executing ping to '{cleaned_host}': {e}")


def get_battery_status(**kwargs: Any) -> ToolResult:
    """Retrieves current battery percentage and AC charging state."""
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return ToolResult.ok(
                {
                    "battery_present": False,
                    "percent": 100,
                    "power_plugged": True,
                    "seconds_left": None,
                    "summary": "No battery detected. Running on direct AC power.",
                }
            )

        secs = (
            battery.secsleft
            if battery.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
            else None
        )
        mins = int(secs // 60) if secs is not None and secs > 0 else None

        state_str = "charging / plugged in" if battery.power_plugged else "discharging / on battery"
        summary = (
            f"Battery is at {round(battery.percent)}% ({state_str}), approx {mins} minutes remaining."
            if mins
            else f"Battery is at {round(battery.percent)}% ({state_str})."
        )

        return ToolResult.ok(
            {
                "battery_present": True,
                "percent": round(battery.percent),
                "power_plugged": bool(battery.power_plugged),
                "seconds_left": secs,
                "minutes_left": mins,
                "summary": summary,
            }
        )
    except Exception as e:
        return ToolResult.fail(f"Failed to query battery status: {e}")


def get_system_status(**kwargs: Any) -> ToolResult:
    """Retrieves overall host health and resource allocation."""
    try:
        mem = psutil.virtual_memory()
        cpu_count = psutil.cpu_count(logical=True)
        ram_used = round((mem.total - mem.available) / (1024**3), 2)
        ram_total = round(mem.total / (1024**3), 2)

        return ToolResult.ok(
            {
                "status": "healthy",
                "cpu_count": cpu_count,
                "ram_used_gb": ram_used,
                "ram_total_gb": ram_total,
                "ram_percent": mem.percent,
                "summary": f"System healthy: {cpu_count} logical CPUs, {ram_used}/{ram_total} GB RAM ({mem.percent}% used).",
            }
        )
    except Exception as e:
        return ToolResult.fail(f"Failed to query system status: {e}")


def get_resource_metrics(**kwargs: Any) -> ToolResult:
    """Retrieves active CPU, RAM, and primary disk utilization metrics."""
    try:
        mem = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=None)
        disk = psutil.disk_usage("C:\\")

        return ToolResult.ok(
            {
                "cpu_percent": cpu_pct,
                "virtual_memory_percent": mem.percent,
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 1),
                "summary": f"CPU load: {cpu_pct}%, RAM: {mem.percent}%, C: disk: {disk.percent}% used.",
            }
        )
    except Exception as e:
        return ToolResult.fail(f"Failed to query resource metrics: {e}")


def get_network_adapter_status(**kwargs: Any) -> ToolResult:
    """Retrieves status and configuration of local physical network adapters."""
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        adapters = []
        for iface_name, stat in stats.items():
            # Skip loopback and internal virtual switches
            if "loopback" in iface_name.lower() or "vethernet" in iface_name.lower():
                continue

            ip_list = []
            if iface_name in addrs:
                for addr in addrs[iface_name]:
                    if addr.family.name in ("AF_INET", "AF_INET6"):
                        ip_list.append(addr.address)

            adapters.append(
                {
                    "name": iface_name,
                    "is_up": stat.isup,
                    "speed_mbps": stat.speed,
                    "addresses": ip_list,
                }
            )

        active_adapters = [a for a in adapters if a["is_up"]]

        return ToolResult.ok(
            {
                "adapters": adapters,
                "active_count": len(active_adapters),
                "total_count": len(adapters),
                "summary": f"Found {len(adapters)} network adapters ({len(active_adapters)} active).",
            }
        )
    except Exception as e:
        return ToolResult.fail(f"Failed to query network adapters: {e}")


def diagnostic_echo(message: str, **kwargs: Any) -> ToolResult:
    """Safe echo tool for verifying tool registry dispatch."""
    return ToolResult.ok({"echo": message, "summary": f"Echo: {message}"})
