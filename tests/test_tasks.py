"""
Tests for Tasks, Reminders, Datetime Parser, and Reminder Scheduler.
"""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from src.agent.tools.datetime_parser import normalize_digits, parse_datetime_expression
from src.agent.tools.handlers.tasks import TaskManager
from src.agent.tools.models import ExecutionStatus
from src.agent.tools.scheduler import ReminderScheduler


def test_datetime_parser_digits_normalization():
    assert normalize_digits("۱۲۳۴۵") == "12345"
    assert normalize_digits("۰۹۸۷۶") == "09876"
    assert normalize_digits("در ۴۵ دقیقه") == "در 45 دقیقه"


def test_datetime_parser_english_and_persian():
    base = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    # English minutes & hours
    dt1 = parse_datetime_expression("in 45 minutes", base_dt=base)
    assert dt1 == base + timedelta(minutes=45)

    dt2 = parse_datetime_expression("in 2 hours", base_dt=base)
    assert dt2 == base + timedelta(hours=2)

    # Persian minutes & hours
    dt3 = parse_datetime_expression("۴۵ دقیقه دیگه", base_dt=base)
    assert dt3 == base + timedelta(minutes=45)

    dt4 = parse_datetime_expression("در ۱۵ دقیقه", base_dt=base)
    assert dt4 == base + timedelta(minutes=15)

    dt5 = parse_datetime_expression("یک ساعت بعد", base_dt=base)
    assert dt5 == base + timedelta(hours=1)

    # Keywords
    dt_tom = parse_datetime_expression("tomorrow", base_dt=base)
    assert dt_tom is not None
    assert dt_tom.day == 14

    dt_farda = parse_datetime_expression("فردا", base_dt=base)
    assert dt_farda is not None
    assert dt_farda.day == 14


def test_task_manager_crud_lifecycle(tmp_path: Path):
    db_path = tmp_path / "test_tasks.db"
    manager = TaskManager(db_path=db_path)

    # 1. Create task
    res = manager.create_task(title="Finish Phase 4", description="Task handler system", due_date="tomorrow")
    assert res.success is True
    assert res.status == ExecutionStatus.COMPLETED
    task_id = res.result["task_id"]
    assert task_id == 1

    # 2. Get task
    get_res = manager.get_task(task_id)
    assert get_res.success is True
    assert get_res.result["title"] == "Finish Phase 4"
    assert get_res.result["status"] == "todo"

    # 3. Update task status (todo -> in_progress)
    up_res = manager.update_task_status(task_id, "in_progress")
    assert up_res.success is True
    assert up_res.result["status"] == "in_progress"

    # 4. Invalid status
    bad_res = manager.update_task_status(task_id, "invalid_status")
    assert bad_res.success is False

    # 5. Complete task
    comp_res = manager.complete_task(task_id)
    assert comp_res.success is True
    assert comp_res.result["status"] == "completed"

    # 6. List tasks
    list_res = manager.list_tasks(status="completed")
    assert list_res.success is True
    assert list_res.result["count"] == 1

    # 7. Delete task - unconfirmed
    del_unconfirmed = manager.delete_task(task_id, confirmed=False)
    assert del_unconfirmed.status == ExecutionStatus.AWAITING_CONFIRMATION
    assert del_unconfirmed.result["action"] == "delete_task"

    # 8. Delete task - confirmed
    del_confirmed = manager.delete_task(task_id, confirmed=True)
    assert del_confirmed.success is True
    assert del_confirmed.result["status"] == "deleted"

    # Verify deleted
    assert manager.get_task(task_id).success is False


def test_reminder_manager_lifecycle(tmp_path: Path):
    db_path = tmp_path / "test_reminders.db"
    manager = TaskManager(db_path=db_path)

    # 1. Create reminder by duration
    res1 = manager.create_reminder(message="Check the oven", duration_minutes=15)
    assert res1.success is True
    rem_id1 = res1.result["reminder_id"]
    assert res1.result["duration_minutes"] == 15

    # 2. Break reminder convenience method
    res2 = manager.schedule_break_reminder(minutes=45)
    assert res2.success is True
    rem_id2 = res2.result["reminder_id"]

    # 3. List reminders
    list_res = manager.list_reminders()
    assert list_res.success is True
    assert list_res.result["count"] == 2

    # 4. Reschedule reminder
    reschedule_res = manager.reschedule_reminder(rem_id1, "in 30 minutes")
    assert reschedule_res.success is True

    # 5. Cancel reminder
    cancel_res = manager.cancel_reminder(rem_id2)
    assert cancel_res.success is True
    assert cancel_res.result["status"] == "cancelled"


def test_reminder_scheduler_background_trigger(tmp_path: Path):
    db_path = tmp_path / "test_scheduler.db"
    manager = TaskManager(db_path=db_path)

    # Create an immediate reminder in the past
    now = datetime.now(timezone.utc)
    past_due = (now - timedelta(seconds=2)).isoformat()
    manager.create_reminder(message="Instant alert", due_time=past_due)

    triggered_reminders = []

    def on_rem(rem):
        triggered_reminders.append(rem)

    scheduler = ReminderScheduler(db_path=db_path, poll_interval=0.2, on_trigger=on_rem)
    scheduler.start()
    assert scheduler.is_running() is True

    # Wait briefly for scheduler to poll
    time.sleep(0.6)
    scheduler.stop()
    assert scheduler.is_running() is False

    assert len(triggered_reminders) == 1
    assert triggered_reminders[0]["message"] == "Instant alert"
