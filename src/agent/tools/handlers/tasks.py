"""
Productivity and Task Management Handler.
Provides SQLite-backed persistence for tasks and reminders, state machine enforcement,
natural-language date parsing (English & Persian), and break scheduling.
Zero external network calls, zero additional GPU memory overhead.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.agent.tools.datetime_parser import parse_datetime_expression
from src.agent.tools.models import ExecutionStatus, ToolResult
from src.core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_TASK_DB_PATH = PROJECT_ROOT / "data" / "assistant_memory.db"

VALID_TASK_STATUSES = {"todo", "in_progress", "completed", "cancelled"}


class TaskManager:
    """Manages SQLite persistence for tasks and scheduled reminders."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_TASK_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        """Initializes tasks and reminders schema if not already present."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'todo',
                    due_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    due_time TEXT NOT NULL,
                    duration_minutes INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    triggered_at TEXT
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status_due ON reminders(status, due_time);")

    # ---------------------------------------------------------
    # Task Operations
    # ---------------------------------------------------------

    def create_task(
        self,
        title: str,
        description: str = "",
        due_date: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Creates a new task with status 'todo'."""
        cleaned_title = str(title).strip()
        if not cleaned_title:
            return ToolResult.fail("Task title cannot be empty.")

        now_utc = datetime.now(timezone.utc).isoformat()
        parsed_due = None
        if due_date:
            parsed_dt = parse_datetime_expression(due_date)
            parsed_due = parsed_dt.isoformat() if parsed_dt else due_date

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO tasks (title, description, status, due_date, created_at, updated_at)
                    VALUES (?, ?, 'todo', ?, ?, ?)
                    """,
                    (cleaned_title, str(description).strip(), parsed_due, now_utc, now_utc),
                )
                task_id = cursor.lastrowid

            return ToolResult.ok(
                {
                    "task_id": task_id,
                    "title": cleaned_title,
                    "description": description,
                    "status": "todo",
                    "due_date": parsed_due,
                    "message": f"Task #{task_id} '{cleaned_title}' created successfully.",
                }
            )
        except Exception as e:
            logger.error("Failed to create task: %s", e)
            return ToolResult.fail(f"Database error creating task: {e}")

    def list_tasks(self, status: str | None = None, **kwargs: Any) -> ToolResult:
        """Lists saved tasks, optionally filtered by status ('todo', 'in_progress', 'completed', 'cancelled')."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if status:
                    stat_clean = status.strip().lower()
                    cursor.execute(
                        "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT 50",
                        (stat_clean,),
                    )
                else:
                    cursor.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 50")
                rows = [dict(row) for row in cursor.fetchall()]

            return ToolResult.ok(
                {
                    "tasks": rows,
                    "count": len(rows),
                    "filter_status": status,
                }
            )
        except Exception as e:
            logger.error("Failed to list tasks: %s", e)
            return ToolResult.fail(f"Database error listing tasks: {e}")

    def get_task(self, task_id: int | str, **kwargs: Any) -> ToolResult:
        """Retrieves a single task by its integer ID."""
        try:
            tid = int(task_id)
        except (ValueError, TypeError):
            return ToolResult.fail(f"Invalid task ID '{task_id}'. Must be an integer.")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE id = ?", (tid,))
                row = cursor.fetchone()

            if not row:
                return ToolResult.fail(f"Task #{tid} not found.")

            return ToolResult.ok(dict(row))
        except Exception as e:
            return ToolResult.fail(f"Database error retrieving task #{tid}: {e}")

    def update_task_status(
        self,
        task_id: int | str,
        status: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Updates the status of a task ('todo', 'in_progress', 'completed', 'cancelled')."""
        try:
            tid = int(task_id)
        except (ValueError, TypeError):
            return ToolResult.fail(f"Invalid task ID '{task_id}'. Must be an integer.")

        stat_clean = str(status).strip().lower()
        if stat_clean not in VALID_TASK_STATUSES:
            valid_list = ", ".join(sorted(VALID_TASK_STATUSES))
            return ToolResult.fail(f"Invalid status '{status}'. Must be one of: {valid_list}.")

        now_utc = datetime.now(timezone.utc).isoformat()
        completed_at = now_utc if stat_clean == "completed" else None

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = ?, updated_at = ?, completed_at = CASE WHEN ? = 'completed' THEN ? ELSE completed_at END
                    WHERE id = ?
                    """,
                    (stat_clean, now_utc, stat_clean, completed_at, tid),
                )
                if cursor.rowcount == 0:
                    return ToolResult.fail(f"Task #{tid} not found.")

            return ToolResult.ok(
                {
                    "task_id": tid,
                    "status": stat_clean,
                    "message": f"Task #{tid} status updated to '{stat_clean}'.",
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Database error updating task #{tid}: {e}")

    def complete_task(self, task_id: int | str, **kwargs: Any) -> ToolResult:
        """Convenience method to mark a task as completed."""
        return self.update_task_status(task_id, status="completed")

    def delete_task(
        self,
        task_id: int | str,
        confirmed: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Deletes a task permanently. Requires explicit user confirmation."""
        try:
            tid = int(task_id)
        except (ValueError, TypeError):
            return ToolResult.fail(f"Invalid task ID '{task_id}'. Must be an integer.")

        # Require confirmation before executing destructive deletion
        if not confirmed:
            return ToolResult.needs_confirmation(
                action_name="delete_task",
                parameters={"task_id": tid, "confirmed": True},
                prompt=f"Are you sure you want to permanently delete task #{tid}?",
            )

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tasks WHERE id = ?", (tid,))
                if cursor.rowcount == 0:
                    return ToolResult.fail(f"Task #{tid} not found.")

            return ToolResult.ok(
                {
                    "task_id": tid,
                    "status": "deleted",
                    "message": f"Task #{tid} was permanently deleted.",
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Database error deleting task #{tid}: {e}")

    # ---------------------------------------------------------
    # Reminder Operations
    # ---------------------------------------------------------

    def create_reminder(
        self,
        message: str,
        due_time: str | None = None,
        duration_minutes: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Schedules a new reminder using relative duration or explicit time expression."""
        clean_msg = str(message).strip()
        if not clean_msg:
            return ToolResult.fail("Reminder message cannot be empty.")

        now = datetime.now(timezone.utc)
        target_dt = None

        if duration_minutes is not None:
            try:
                mins = int(duration_minutes)
                target_dt = now + timedelta(minutes=mins)
            except (ValueError, TypeError):
                return ToolResult.fail("duration_minutes must be an integer.")
        elif due_time:
            target_dt = parse_datetime_expression(due_time, base_dt=now)

        if target_dt is None:
            return ToolResult.fail("Could not determine reminder time. Provide duration_minutes or due_time.")

        target_iso = target_dt.isoformat()
        now_iso = now.isoformat()
        dur_mins = int((target_dt - now).total_seconds() // 60) if target_dt > now else 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO reminders (message, due_time, duration_minutes, status, created_at)
                    VALUES (?, ?, ?, 'pending', ?)
                    """,
                    (clean_msg, target_iso, dur_mins, now_iso),
                )
                rem_id = cursor.lastrowid

            return ToolResult.ok(
                {
                    "reminder_id": rem_id,
                    "message": clean_msg,
                    "due_time": target_iso,
                    "duration_minutes": dur_mins,
                    "status": "pending",
                    "message_summary": f"Reminder #{rem_id} scheduled for {target_iso} ({dur_mins} minutes from now).",
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Database error scheduling reminder: {e}")

    def list_reminders(
        self,
        include_completed: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Lists upcoming pending reminders, or all reminders if include_completed is True."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if include_completed:
                    cursor.execute("SELECT * FROM reminders ORDER BY due_time ASC LIMIT 50")
                else:
                    cursor.execute("SELECT * FROM reminders WHERE status = 'pending' ORDER BY due_time ASC LIMIT 50")
                rows = [dict(row) for row in cursor.fetchall()]

            return ToolResult.ok(
                {
                    "reminders": rows,
                    "count": len(rows),
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Database error listing reminders: {e}")

    def cancel_reminder(self, reminder_id: int | str, **kwargs: Any) -> ToolResult:
        """Cancels a pending reminder."""
        try:
            rid = int(reminder_id)
        except (ValueError, TypeError):
            return ToolResult.fail(f"Invalid reminder ID '{reminder_id}'. Must be an integer.")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
                    (rid,),
                )
                if cursor.rowcount == 0:
                    return ToolResult.fail(f"Pending reminder #{rid} not found.")

            return ToolResult.ok(
                {
                    "reminder_id": rid,
                    "status": "cancelled",
                    "message": f"Reminder #{rid} was cancelled.",
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Database error cancelling reminder #{rid}: {e}")

    def reschedule_reminder(
        self,
        reminder_id: int | str,
        new_due_time: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Reschedules a reminder to a new time expression."""
        try:
            rid = int(reminder_id)
        except (ValueError, TypeError):
            return ToolResult.fail(f"Invalid reminder ID '{reminder_id}'. Must be an integer.")

        parsed_dt = parse_datetime_expression(new_due_time)
        if not parsed_dt:
            return ToolResult.fail(f"Could not parse new due time '{new_due_time}'.")

        new_iso = parsed_dt.isoformat()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE reminders SET due_time = ?, status = 'pending' WHERE id = ?",
                    (new_iso, rid),
                )
                if cursor.rowcount == 0:
                    return ToolResult.fail(f"Reminder #{rid} not found.")

            return ToolResult.ok(
                {
                    "reminder_id": rid,
                    "due_time": new_iso,
                    "message": f"Reminder #{rid} rescheduled to {new_iso}.",
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Database error rescheduling reminder #{rid}: {e}")

    def schedule_break_reminder(
        self,
        minutes: int | str = 45,
        message: str = "Time to take a break! Stretch your legs and rest your eyes.",
        **kwargs: Any,
    ) -> ToolResult:
        """Convenience method to set a break reminder after a specified number of minutes (default 45)."""
        try:
            mins = int(minutes)
        except (ValueError, TypeError):
            mins = 45

        return self.create_reminder(
            message=message,
            duration_minutes=mins,
        )
