"""
Background Reminder Scheduler.
Runs a lightweight daemon thread to monitor and trigger due reminders.
Consumes zero VRAM and minimal CPU cycles.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Lightweight background thread that polls for due reminders."""

    def __init__(
        self,
        db_path: Path | str,
        poll_interval: float = 5.0,
        on_trigger: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.db_path = Path(db_path)
        self.poll_interval = max(1.0, float(poll_interval))
        self.on_trigger = on_trigger
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Starts the background scheduler thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ReminderSchedulerThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("ReminderScheduler started with %.1fs interval.", self.poll_interval)

    def stop(self, timeout: float = 2.0) -> None:
        """Stops the scheduler thread cleanly."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("ReminderScheduler stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def check_due_reminders(self) -> list[dict[str, Any]]:
        """Checks for and triggers any due reminders synchronously."""
        now_iso = datetime.now(timezone.utc).isoformat()
        triggered_list: list[dict[str, Any]] = []

        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, message, due_time, duration_minutes, status, created_at
                    FROM reminders
                    WHERE status = 'pending' AND due_time <= ?
                    ORDER BY due_time ASC
                    """,
                    (now_iso,),
                )
                rows = cursor.fetchall()
                for row in rows:
                    rem = dict(row)
                    rem_id = rem["id"]
                    cursor.execute(
                        """
                        UPDATE reminders
                        SET status = 'triggered', triggered_at = ?
                        WHERE id = ?
                        """,
                        (now_iso, rem_id),
                    )
                    triggered_list.append(rem)

            for rem in triggered_list:
                logger.info("Reminder #%s triggered: %s", rem["id"], rem["message"])
                if self.on_trigger:
                    try:
                        self.on_trigger(rem)
                    except Exception as e:
                        logger.error("Error in on_trigger callback for reminder #%s: %s", rem["id"], e)

        except Exception as e:
            logger.error("Error checking due reminders: %s", e)

        return triggered_list

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.check_due_reminders()
            self._stop_event.wait(timeout=self.poll_interval)
