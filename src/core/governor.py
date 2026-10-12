"""
Resource Governor for local inference.
Enforces process priority, tracks CPU/RAM/VRAM consumption, and coordinates idle unloading.
"""

import logging
import os
import subprocess
import threading
import time
from typing import Callable, NamedTuple
import psutil

from src.core.config import ResourceGovernorConfig

logger = logging.getLogger("assistant.governor")


class SystemTelemetry(NamedTuple):
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float
    gpu_vram_used_mb: float | None
    gpu_vram_total_mb: float | None


class ResourceGovernor:
    """Monitors system load and enforces background execution etiquette."""

    def __init__(
        self,
        config: ResourceGovernorConfig,
        on_idle_timeout: Callable[[], None] | None = None,
    ):
        self.config = config
        self.on_idle_timeout = on_idle_timeout
        self.last_activity_time = time.time()
        self._idle_monitor_active = False
        self._idle_thread: threading.Thread | None = None

    def apply_process_priority(self, pid: int) -> bool:
        """Sets Windows OS priority class on the target worker process."""
        try:
            p = psutil.Process(pid)
            if os.name == "nt":
                priority_map = {
                    "IDLE": psutil.IDLE_PRIORITY_CLASS,
                    "BELOW_NORMAL": psutil.BELOW_NORMAL_PRIORITY_CLASS,
                    "NORMAL": psutil.NORMAL_PRIORITY_CLASS,
                }
                target_priority = priority_map.get(
                    self.config.process_priority, psutil.BELOW_NORMAL_PRIORITY_CLASS
                )
                p.nice(target_priority)
                logger.info("Enforced Windows priority %s on PID %d", self.config.process_priority, pid)
                return True
        except Exception as e:
            logger.warning("Could not set process priority for PID %d: %s", pid, e)
            return False
        return False

    def touch_activity(self) -> None:
        """Records user or model interaction to reset the idle countdown."""
        self.last_activity_time = time.time()

    def get_system_telemetry(self) -> SystemTelemetry:
        """Collects lightweight hardware telemetry."""
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        vram_used, vram_total = self._query_gpu_vram()

        return SystemTelemetry(
            cpu_percent=cpu_pct,
            ram_used_gb=round((mem.total - mem.available) / (1024**3), 2),
            ram_total_gb=round(mem.total / (1024**3), 2),
            ram_percent=mem.percent,
            gpu_vram_used_mb=vram_used,
            gpu_vram_total_mb=vram_total,
        )

    def _query_gpu_vram(self) -> tuple[float | None, float | None]:
        """Queries nvidia-smi for VRAM telemetry without throwing on error."""
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                text=True,
                timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ).strip()
            if out:
                parts = out.split(",")
                if len(parts) == 2:
                    return float(parts[0].strip()), float(parts[1].strip())
        except Exception:
            pass
        return None, None

    def start_idle_monitor(self) -> None:
        """Spawns background timer to unload model on inactivity."""
        if self._idle_monitor_active:
            return
        self._idle_monitor_active = True
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self._idle_thread.start()

    def stop_idle_monitor(self) -> None:
        self._idle_monitor_active = False

    def _idle_loop(self) -> None:
        while self._idle_monitor_active:
            time.sleep(5)
            idle_duration = time.time() - self.last_activity_time
            if idle_duration >= self.config.idle_timeout_seconds:
                logger.info("Idle timeout triggered (%ds inactive). Requesting model unload.", int(idle_duration))
                if self.on_idle_timeout:
                    try:
                        self.on_idle_timeout()
                    except Exception as e:
                        logger.error("Error executing on_idle_timeout callback: %s", e)
                # Reset activity to avoid repeat firings until new activity happens
                self.last_activity_time = time.time()
