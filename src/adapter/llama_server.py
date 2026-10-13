"""
LlamaServerManager: Controls the lifecycle of local llama-server.exe.
Ensures loopback binding, explicit hardware budgeting, priority enforcement, and clean shutdown.
"""

import logging
import os
import subprocess
import time
from pathlib import Path
import httpx

from src.core.config import AssistantSettings
from src.core.governor import ResourceGovernor

logger = logging.getLogger("assistant.server")


class LlamaServerManager:
    """Manages the local llama-server child process."""

    def __init__(self, settings: AssistantSettings, governor: ResourceGovernor | None = None):
        self.settings = settings
        self.governor = governor
        self.process: subprocess.Popen | None = None
        self._server_url = f"http://{settings.network.server_host}:{settings.network.server_port}"

    @property
    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    @property
    def server_url(self) -> str:
        return self._server_url

    def check_health(self) -> bool:
        """Checks if llama-server is currently answering on the health endpoint."""
        try:
            with httpx.Client(timeout=1.5, trust_env=False) as client:
                resp = client.get(f"{self._server_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    def ensure_server_running(self, timeout_seconds: int = 45) -> bool:
        """Ensures that llama-server is healthy, starting it if not already active."""
        if self.check_health():
            logger.info("llama-server is already active and healthy on %s.", self._server_url)
            return True
        return self.start(timeout_seconds=timeout_seconds)

    def start(self, timeout_seconds: int = 45) -> bool:
        """Starts llama-server on loopback with configured resource bounds."""
        if self.is_running or self.check_health():
            logger.info("llama-server is already running.")
            return True

        server_exe = self.settings.llama_bin_dir / "llama-server.exe"
        model_path = self.settings.model_path

        if not server_exe.exists():
            raise FileNotFoundError(f"llama-server executable not found at: {server_exe}")
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found at: {model_path}")

        # Assemble explicit command flags
        cmd = [
            str(server_exe),
            "-m", str(model_path),
            "-ngl", str(self.settings.governor.gpu_layers),
            "-t", str(self.settings.governor.cpu_threads),
            "-c", str(self.settings.governor.max_context_tokens),
            "--host", self.settings.network.server_host,
            "--port", str(self.settings.network.server_port),
            "--n-predict", str(self.settings.governor.max_output_tokens),
            "--log-disable",  # Keeps stdout clean; can redirect to file if needed
        ]

        logger.info(
            "Starting llama-server: GPU layers=%d, CPU threads=%d, Context=%d, Port=%d",
            self.settings.governor.gpu_layers,
            self.settings.governor.cpu_threads,
            self.settings.governor.max_context_tokens,
            self.settings.network.server_port,
        )

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

        # Enforce OS-level process priority immediately
        if self.governor and self.process.pid:
            self.governor.apply_process_priority(self.process.pid)

        # Wait for health endpoint to respond
        start_t = time.time()
        health_url = f"{self._server_url}/health"
        logger.info("Waiting for llama-server health readiness at %s...", health_url)

        with httpx.Client(timeout=2.0, trust_env=False) as client:
            while time.time() - start_t < timeout_seconds:
                if self.process.poll() is not None:
                    exit_code = self.process.returncode
                    self.process = None
                    raise RuntimeError(f"llama-server process exited unexpectedly with code: {exit_code}")
                try:
                    resp = client.get(health_url)
                    if resp.status_code == 200:
                        logger.info("llama-server is healthy and ready (PID %d).", self.process.pid)
                        return True
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass
                time.sleep(0.5)

        self.stop()
        raise TimeoutError(f"llama-server failed to respond within {timeout_seconds} seconds.")

    def stop(self) -> None:
        """Cleanly terminates the local llama-server process."""
        if self.process is None:
            return

        pid = self.process.pid
        logger.info("Stopping llama-server (PID %d)...", pid)

        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except (subprocess.TimeoutExpired, Exception):
            logger.warning("llama-server did not terminate gracefully. Forcing kill...")
            try:
                self.process.kill()
            except Exception:
                pass

        self.process = None
        logger.info("llama-server stopped cleanly.")
