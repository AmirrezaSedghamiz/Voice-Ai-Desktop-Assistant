"""
Deterministic Evaluators for Quality Lab.
Performs strict, reproducible assertions on tool selection, parameter constraints,
policy enforcement decisions, database state transitions, and Unicode consistency.
"""

from __future__ import annotations

from typing import Any
from quality_lab.models import FailureCategory, TestResult, TestStatus, Severity, TestMode
from quality_lab.evaluators.speech_metrics import normalize_evaluation_text


class DeterministicEvaluator:
    """Evaluates observable state changes and structured contracts deterministically."""

    @staticmethod
    def evaluate_tool_decision(
        test_id: str,
        name: str,
        suite: str,
        duration: float,
        expected_tool: str | None,
        expected_params: dict[str, Any] | None,
        observed_tool: str | None,
        observed_params: dict[str, Any] | None,
        expected_policy_decision: str = "PERMITTED",
        observed_policy_decision: str = "PERMITTED",
        severity: Severity = Severity.HIGH,
        is_release_gate: bool = True,
    ) -> TestResult:
        """Evaluates whether the orchestrator and policy engine correctly invoked/blocked a tool."""
        # 1. Check policy gate match
        if expected_policy_decision != observed_policy_decision:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite=suite,
                status=TestStatus.FAILED,
                mode=TestMode.INTEGRATION,
                duration_seconds=duration,
                expected_outcome=f"Policy decision {expected_policy_decision}",
                observed_outcome=f"Policy decision {observed_policy_decision}",
                failure_category=FailureCategory.SECURITY_VIOLATION if expected_policy_decision == "BLOCKED" else FailureCategory.ASSERTION_FAILED,
                diagnostic_message=f"Policy decision mismatch: expected {expected_policy_decision}, got {observed_policy_decision}",
                severity=severity,
                is_release_gate=is_release_gate,
            )

        # 2. Check tool selection
        if expected_tool is not None:
            if observed_tool != expected_tool:
                return TestResult(
                    run_id="",
                    test_id=test_id,
                    name=name,
                    suite=suite,
                    status=TestStatus.FAILED,
                    mode=TestMode.INTEGRATION,
                    duration_seconds=duration,
                    expected_outcome=f"Action '{expected_tool}'",
                    observed_outcome=f"Action '{observed_tool}'",
                    failure_category=FailureCategory.ASSERTION_FAILED,
                    diagnostic_message=f"Tool selection error: expected {expected_tool}, got {observed_tool}",
                    severity=severity,
                    is_release_gate=is_release_gate,
                )

        # 3. Check parameters
        if expected_params and observed_params is not None:
            for key, val in expected_params.items():
                if key not in observed_params:
                    return TestResult(
                        run_id="",
                        test_id=test_id,
                        name=name,
                        suite=suite,
                        status=TestStatus.FAILED,
                        mode=TestMode.INTEGRATION,
                        duration_seconds=duration,
                        expected_outcome=f"Parameter '{key}': {val}",
                        observed_outcome=f"Observed parameters: {observed_params}",
                        failure_category=FailureCategory.ASSERTION_FAILED,
                        diagnostic_message=f"Missing parameter '{key}' in tool arguments",
                        severity=severity,
                        is_release_gate=is_release_gate,
                    )

                obs_val = observed_params[key]
                if obs_val == "[MEMORY_CONTENT_OMITTED]":
                    # Intentional privacy redaction applied by the orchestrator audit logger
                    continue

                if isinstance(val, str) and isinstance(obs_val, str):
                    if normalize_evaluation_text(val) != normalize_evaluation_text(obs_val):
                        return TestResult(
                            run_id="",
                            test_id=test_id,
                            name=name,
                            suite=suite,
                            status=TestStatus.FAILED,
                            mode=TestMode.INTEGRATION,
                            duration_seconds=duration,
                            expected_outcome=f"Parameter '{key}' = '{val}'",
                            observed_outcome=f"Parameter '{key}' = '{obs_val}'",
                            failure_category=FailureCategory.ASSERTION_FAILED,
                            diagnostic_message=f"Parameter value mismatch for '{key}': expected '{val}', got '{obs_val}'",
                            severity=severity,
                            is_release_gate=is_release_gate,
                        )
                elif val != obs_val:
                    return TestResult(
                        run_id="",
                        test_id=test_id,
                        name=name,
                        suite=suite,
                        status=TestStatus.FAILED,
                        mode=TestMode.INTEGRATION,
                        duration_seconds=duration,
                        expected_outcome=f"Parameter '{key}' = {val}",
                        observed_outcome=f"Parameter '{key}' = {obs_val}",
                        failure_category=FailureCategory.ASSERTION_FAILED,
                        diagnostic_message=f"Parameter value mismatch for '{key}': expected {val}, got {obs_val}",
                        severity=severity,
                        is_release_gate=is_release_gate,
                    )

        return TestResult(
            run_id="",
            test_id=test_id,
            name=name,
            suite=suite,
            status=TestStatus.PASSED,
            mode=TestMode.INTEGRATION,
            duration_seconds=duration,
            expected_outcome=f"Action '{expected_tool}' with valid arguments",
            observed_outcome=f"Executed '{observed_tool}' ({observed_policy_decision})",
            failure_category=FailureCategory.NONE,
            diagnostic_message="All deterministic contract constraints satisfied.",
            severity=severity,
            is_release_gate=is_release_gate,
        )

    @staticmethod
    def evaluate_state_change(
        test_id: str,
        name: str,
        suite: str,
        duration: float,
        expected_state: str,
        verified_state: bool,
        diagnostic: str = "",
        severity: Severity = Severity.HIGH,
        is_release_gate: bool = True,
    ) -> TestResult:
        """Evaluates whether an intended persistent state change was verified in storage."""
        if not verified_state:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite=suite,
                status=TestStatus.FAILED,
                mode=TestMode.INTEGRATION,
                duration_seconds=duration,
                expected_outcome=expected_state,
                observed_outcome="State change not verified in storage",
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=diagnostic or f"Failed to verify state change: {expected_state}",
                severity=severity,
                is_release_gate=is_release_gate,
            )

        return TestResult(
            run_id="",
            test_id=test_id,
            name=name,
            suite=suite,
            status=TestStatus.PASSED,
            mode=TestMode.INTEGRATION,
            duration_seconds=duration,
            expected_outcome=expected_state,
            observed_outcome="State change verified in storage",
            failure_category=FailureCategory.NONE,
            diagnostic_message="Verified persistent state transition successfully.",
            severity=severity,
            is_release_gate=is_release_gate,
        )
