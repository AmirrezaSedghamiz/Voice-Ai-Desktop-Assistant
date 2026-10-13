"""
Disposable Test Sandbox & Isolated Mock Infrastructure.
Ensures zero destructive actions against real user files, system registry,
production task databases, or active memory tables.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from src.adapter.llm_client import InferenceMetrics, LocalLlmClient
from src.agent.audit_log import AuditLogger
from src.agent.orchestrator import SafeAgentOrchestrator
from src.agent.policy_engine import PolicyEngine
from src.agent.tools.handlers.tasks import TaskManager
from src.core.config import AssistantSettings, get_default_settings
from src.memory.store import MemoryStore


class DisposableSandbox:
    """Manages isolated temporary filesystem directories and ephemeral SQLite databases."""

    def __init__(self, prefix: str = "david_test_"):
        self.temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.data_dir = self.temp_dir / "data"
        self.logs_dir = self.temp_dir / "logs"
        self.docs_dir = self.temp_dir / "documents"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        self.memory_db_path = self.data_dir / "test_memory.db"
        self.tasks_db_path = self.data_dir / "test_tasks.db"

        # Create safe canary files for file-search tests
        (self.docs_dir / "report_2026.txt").write_text("Quarterly productivity notes.", encoding="utf-8")
        (self.docs_dir / "gtd_todos.md").write_text("1. Review architecture\n2. Run tests", encoding="utf-8")
        (self.docs_dir / "persian_notes.txt").write_text("یادداشت‌های مهم برای دستیار دیوید", encoding="utf-8")

        self.memory_store = MemoryStore(db_path=self.memory_db_path)
        self.task_manager = TaskManager(db_path=self.tasks_db_path)
        self.policy_engine = PolicyEngine(authorized_roots=[self.temp_dir, self.docs_dir])
        self.audit_logger = AuditLogger(log_dir=self.logs_dir)

    def cleanup(self) -> None:
        """Closes open database connections and removes temporary directories."""
        try:
            self.memory_store.close()
        except Exception:
            pass
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def __enter__(self) -> DisposableSandbox:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()


def create_mock_llm_client(responses: list[str] | str | None = None) -> MagicMock:
    """Creates a deterministic mock LLM client returning planned responses and metrics."""
    mock_client = MagicMock(spec=LocalLlmClient)
    metrics = InferenceMetrics()
    metrics.tokens_per_second = 50.0
    metrics.total_generation_time = 0.05
    metrics.prompt_tokens = 32
    metrics.completion_tokens = 16

    if responses is None:
        mock_client.chat_completion.return_value = ("I can assist you.", metrics)
    elif isinstance(responses, str):
        mock_client.chat_completion.return_value = (responses, metrics)
    else:
        # Multiple sequential responses
        iterator = iter(responses)

        def side_effect(*args: Any, **kwargs: Any) -> tuple[str, InferenceMetrics]:
            try:
                resp = next(iterator)
            except StopIteration:
                resp = "Done."
            return (resp, metrics)

        mock_client.chat_completion.side_effect = side_effect

    return mock_client
