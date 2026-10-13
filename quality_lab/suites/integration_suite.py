"""
Quality Lab Suite: Task Handlers & Persistence Integration Suite.
Evaluates SQLite persistence, task CRUD, reminders, allowed application launching,
scoped file search, confirmation enforcement, and telemetry diagnostics in disposable sandboxes.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from quality_lab.config import QualityLabConfig
from quality_lab.evaluators.deterministic import DeterministicEvaluator
from quality_lab.fixtures.mock_environment import DisposableSandbox
from quality_lab.models import FailureCategory, Severity, SuiteResult, TestMode, TestResult, TestStatus
from src.agent.orchestrator import SafeToolRegistry
from src.agent.tools.models import ExecutionStatus, ToolResult


class IntegrationSuite:
    """Evaluates task management, memory persistence, handlers, and scheduler."""

    def __init__(self, config: QualityLabConfig):
        self.config = config

    def run(self) -> SuiteResult:
        suite = SuiteResult(suite_name="integration", status=TestStatus.PASSED)
        cases = [
            self._test_task_lifecycle_crud_and_persistence,
            self._test_task_deletion_confirmation_gate,
            self._test_reminder_creation_and_due_time_persistence,
            self._test_memory_fact_remember_and_fts5_recall,
            self._test_memory_forget_fact_lifecycle,
            self._test_note_saving_and_fts_search,
            self._test_allowed_application_launching_mock,
            self._test_scoped_file_search_within_sandbox,
            self._test_dictation_confirmation_requirement,
            self._test_diagnostic_telemetry_handlers,
        ]

        for case_fn in cases:
            try:
                res = case_fn()
            except Exception as e:
                diag = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                res = TestResult(
                    run_id="",
                    test_id=getattr(case_fn, "__name__", "UNKNOWN"),
                    name=getattr(case_fn, "__name__", "UNKNOWN"),
                    suite="integration",
                    status=TestStatus.FAILED,
                    mode=TestMode.INTEGRATION,
                    duration_seconds=0.01,
                    failure_category=FailureCategory.ASSERTION_FAILED,
                    diagnostic_message=diag,
                    severity=Severity.HIGH,
                )
            suite.results.append(res)

        suite.recompute_summary()
        return suite

    def _test_task_lifecycle_crud_and_persistence(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-TASK-CRUD-001"
        name = "Task Management CRUD & SQLite Persistence"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            # 1. Create task
            res_create = tools.create_task(title="Deploy Quality Lab", due_date="tomorrow")
            if not res_create.success:
                return TestResult(
                    run_id="",
                    test_id=test_id,
                    name=name,
                    suite="integration",
                    status=TestStatus.FAILED,
                    mode=TestMode.INTEGRATION,
                    duration_seconds=round(time.time() - start_t, 4),
                    failure_category=FailureCategory.ASSERTION_FAILED,
                    diagnostic_message=f"Task creation failed: {res_create.error}",
                    severity=Severity.HIGH,
                )

            task_id = res_create.result.get("task_id")
            assert task_id is not None

            # 2. Verify state in SQLite
            persisted = sandbox.task_manager.get_task(task_id)
            assert persisted.success is True
            assert persisted.result["title"] == "Deploy Quality Lab"
            assert persisted.result["status"] in ("todo", "pending")

            # 3. Complete task
            res_comp = tools.complete_task(task_id=task_id)
            assert res_comp.success is True

            # 4. Verify updated state in SQLite
            updated = sandbox.task_manager.get_task(task_id)
            assert updated.result["status"] == "completed"

            return DeterministicEvaluator.evaluate_state_change(
                test_id=test_id,
                name=name,
                suite="integration",
                duration=round(time.time() - start_t, 4),
                expected_state=f"Task #{task_id} created, queried, and marked completed in SQLite",
                verified_state=(updated.result["status"] == "completed"),
            )

    def _test_task_deletion_confirmation_gate(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-TASK-DELETE-GATE-002"
        name = "Task Deletion Confirmation Gate"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            res_create = tools.create_task(title="Temporary Task")
            task_id = res_create.result.get("task_id")

            # Attempt deletion without confirmed=True
            res_del_unconfirmed = tools.delete_task(task_id=task_id, confirmed=False)
            assert res_del_unconfirmed.status == ExecutionStatus.AWAITING_CONFIRMATION

            # Verify task was NOT deleted in database
            check = sandbox.task_manager.get_task(task_id)
            assert check.success is True, "Task was deleted prematurely without confirmation"

            # Delete with confirmed=True
            res_del_confirmed = tools.delete_task(task_id=task_id, confirmed=True)
            assert res_del_confirmed.success is True

            # Verify task is deleted
            check_after = sandbox.task_manager.get_task(task_id)
            assert check_after.success is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Deletion blocked until confirmed=True",
                observed_outcome="Task preserved on unconfirmed call, deleted on confirmed call",
                severity=Severity.HIGH,
            )

    def _test_reminder_creation_and_due_time_persistence(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-REMINDER-SCHED-003"
        name = "Reminder Creation and Due Time Persistence"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            res = tools.create_reminder(message="Check experiment telemetry", duration_minutes=30)
            assert res.success is True
            rem_id = res.result.get("reminder_id")

            # Check reminder exists in list
            rems = tools.list_reminders()
            assert rems.success is True
            all_rems = rems.result.get("reminders", [])
            found = any(r["id"] == rem_id for r in all_rems)

            return DeterministicEvaluator.evaluate_state_change(
                test_id=test_id,
                name=name,
                suite="integration",
                duration=round(time.time() - start_t, 4),
                expected_state=f"Reminder #{rem_id} scheduled and persisted",
                verified_state=found,
            )

    def _test_memory_fact_remember_and_fts5_recall(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-MEMORY-FTS5-004"
        name = "Persistent SQLite Memory Store & FTS5 Recall"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            # Store facts in English and Persian
            res_en = tools.remember_fact(key="favorite_editor", value="Antigravity IDE", category="preference")
            assert res_en["status"] in ("created", "updated")

            res_fa = tools.remember_fact(key="preferred_language", value="فارسی و انگلیسی", category="profile")
            assert res_fa["status"] in ("created", "updated")

            # Recall via FTS5 query
            hits_en = tools.recall_facts(query="Antigravity")
            assert hits_en["status"] == "ok"
            assert hits_en["count"] >= 1
            assert any("Antigravity" in r["content"] for r in hits_en["results"])

            hits_fa = tools.recall_facts(query="فارسی")
            assert hits_fa["status"] == "ok"
            assert hits_fa["count"] >= 1

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Facts persisted in SQLite and recalled via FTS5 index",
                observed_outcome=f"English and Persian facts indexed and recalled (hits: {hits_en['count']} en, {hits_fa['count']} fa)",
                severity=Severity.HIGH,
            )

    def _test_memory_forget_fact_lifecycle(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-MEMORY-FORGET-005"
        name = "Memory Fact Deactivation Lifecycle"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            tools.remember_fact(key="temp_preference", value="dark_mode")
            res_forget = tools.forget_fact(key="temp_preference")
            assert res_forget["status"] == "deleted"

            # Verify it is no longer recalled
            hits = tools.recall_facts(query="temp_preference")
            assert hits["count"] == 0

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Fact deactivated and excluded from subsequent recall queries",
                observed_outcome="Fact deactivated cleanly",
                severity=Severity.MEDIUM,
            )

    def _test_note_saving_and_fts_search(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-NOTES-FTS-006"
        name = "Durable Note Saving and Full-Text Search"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            res = tools.save_note(
                title="Security Protocol",
                content="Always verify offline boundary before deployment.",
                category="work",
            )
            assert res["status"] == "saved"

            search = tools.recall_facts(query="offline boundary")
            assert search["status"] == "ok"
            assert any("Security Protocol" in r["key_or_title"] for r in search["results"])

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Note saved to database and indexed in FTS5",
                observed_outcome="Note saved and matched by full-text search query",
                severity=Severity.HIGH,
            )

    def _test_allowed_application_launching_mock(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-APP-LAUNCH-007"
        name = "Approved Application Launch Handler (Mocked OS Execution)"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            # Test launching approved app with mocked subprocess.Popen to prevent actual GUI popups during test
            with patch("subprocess.Popen") as mock_popen:
                res_calc = tools.launch_application(app_name="calculator")
                assert res_calc.success is True
                assert res_calc.result["executable"] == "calc.exe"
                mock_popen.assert_called_once()

            # Launching unauthorized app must fail
            res_bad = tools.launch_application(app_name="powershell")
            assert res_bad.success is False
            assert "not in the approved allowlist" in res_bad.error

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Allowed utility launched; unauthorized utility rejected",
                observed_outcome="calculator authorized, powershell rejected",
                severity=Severity.HIGH,
            )

    def _test_scoped_file_search_within_sandbox(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-FILE-SEARCH-008"
        name = "Scoped Filesystem Search Within Authorized Roots"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            # Search in authorized sandbox
            res = tools.search_files(pattern="report", root_dir=str(sandbox.docs_dir))
            assert res.success is True
            assert res.result["count"] >= 1
            assert any("report_2026.txt" in f["name"] for f in res.result["results"])

            # Search outside authorized roots must fail policy check
            res_unauth = tools.search_files(pattern="passwords", root_dir="C:\\Windows\\System32")
            assert res_unauth.success is False
            assert "Filesystem Violation" in res_unauth.error

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Authorized path searched; unauthorized path blocked by policy",
                observed_outcome="Canary file found; System32 access denied",
                severity=Severity.HIGH,
            )

    def _test_dictation_confirmation_requirement(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-DICTATION-GATE-009"
        name = "Dictation Text Insertion Confirmation Requirement"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            # Unconfirmed call must return AWAITING_CONFIRMATION
            res_unconfirmed = tools.insert_text(text="Sample text to type", confirmed=False)
            assert res_unconfirmed.status == ExecutionStatus.AWAITING_CONFIRMATION

            # Confirmed call with mocked pyautogui
            with patch("src.agent.tools.handlers.dictation.pyautogui", create=True) as mock_gui:
                res_confirmed = tools.insert_text(text="Sample text to type", confirmed=True)
                assert res_confirmed.success is True

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Text insertion requires confirmation before typing",
                observed_outcome="Awaiting confirmation triggered as required",
                severity=Severity.HIGH,
            )

    def _test_diagnostic_telemetry_handlers(self) -> TestResult:
        start_t = time.time()
        test_id = "INT-DIAG-TELEMETRY-010"
        name = "System Diagnostics and Battery Telemetry Handlers"

        with DisposableSandbox() as sandbox:
            tools = SafeToolRegistry(
                memory_store=sandbox.memory_store,
                task_manager=sandbox.task_manager,
                policy_engine=sandbox.policy_engine,
            )

            # Battery status check
            bat = tools.get_battery_status()
            assert isinstance(bat, dict)
            assert "battery_present" in bat

            # System status check
            sys_stat = tools.get_system_status()
            assert isinstance(sys_stat, dict)
            assert "cpu_count" in sys_stat
            assert "ram_total_gb" in sys_stat

            # Spoken response formatting
            formatted_bat = SafeToolRegistry.format_tool_result("get_battery_status", bat)
            assert len(formatted_bat) > 5

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="integration",
                status=TestStatus.PASSED,
                mode=TestMode.INTEGRATION,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Telemetry handlers return structured dictionaries and spoken summaries",
                observed_outcome=formatted_bat,
                severity=Severity.MEDIUM,
            )
