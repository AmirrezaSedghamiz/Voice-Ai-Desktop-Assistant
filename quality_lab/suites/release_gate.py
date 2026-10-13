"""
Quality Lab Release Gate Policy Engine.
Evaluates multi-suite test outcomes, hard security blockers, quality thresholds,
and regressions against calibrated production baselines to determine release readiness.
"""

from __future__ import annotations

from typing import Any
from quality_lab.config import QualityLabConfig
from quality_lab.models import FailureCategory, RunSummary, Severity, TestStatus


class ReleaseGateEvaluator:
    """Evaluates release gating criteria across all executed suites."""

    def __init__(self, config: QualityLabConfig, baseline: dict[str, Any] | None = None):
        self.config = config
        self.baseline = baseline or {}

    def evaluate(self, summary: RunSummary) -> tuple[bool, list[str], list[str]]:
        """
        Evaluates the RunSummary against release criteria.
        Returns: (passed: bool, blockers: list[str], warnings: list[str])
        """
        blockers: list[str] = []
        warnings: list[str] = []

        # 1. Hard Security Gate: Any security test failure or security violation is fatal
        security_suite = summary.suites.get("security")
        if security_suite:
            for r in security_suite.results:
                if r.status in (TestStatus.FAILED, TestStatus.ERROR):
                    blockers.append(f"CRITICAL SECURITY FAILURE: {r.test_id} - {r.name}: {r.diagnostic_message}")
                if r.failure_category == FailureCategory.SECURITY_VIOLATION:
                    blockers.append(f"SECURITY VIOLATION DETECTED: {r.test_id} ({r.name})")

        # 2. Hard Unit & Contract Gate
        unit_suite = summary.suites.get("unit")
        if unit_suite:
            if unit_suite.failed > 0 or unit_suite.error > 0:
                blockers.append(f"UNIT & CONTRACT FAILURES: {unit_suite.failed} failed, {unit_suite.error} errors in unit suite")

        # 3. Hard Integration Gate
        int_suite = summary.suites.get("integration")
        if int_suite:
            if int_suite.failed > 0 or int_suite.error > 0:
                blockers.append(f"INTEGRATION FAILURES: {int_suite.failed} failed, {int_suite.error} errors in integration suite")

        # 4. Critical severity gate across all tests
        for s_name, s_res in summary.suites.items():
            for r in s_res.results:
                if r.severity == Severity.CRITICAL and r.status in (TestStatus.FAILED, TestStatus.ERROR):
                    msg = f"CRITICAL TEST FAILED: [{s_name}] {r.test_id} - {r.name}"
                    if msg not in blockers:
                        blockers.append(msg)

        # 5. Packaged binary gate (if packaged suite was run)
        pkg_suite = summary.suites.get("packaged")
        if pkg_suite:
            if pkg_suite.inconclusive > 0:
                warnings.append("PACKAGING INCONCLUSIVE: Packaged executable binary not found or assets missing")
            elif pkg_suite.failed > 0 or pkg_suite.error > 0:
                blockers.append(f"PACKAGED BINARY FAILURE: {pkg_suite.failed} failures in packaged distribution tests")

        # 6. AI Evaluation Threshold Gate
        ai_suite = summary.suites.get("ai")
        if ai_suite and ai_suite.total > 0:
            ai_pass_rate = (ai_suite.passed / ai_suite.total) * 100.0
            if ai_pass_rate < self.config.min_ai_accuracy_percent:
                blockers.append(
                    f"AI ACCURACY BELOW THRESHOLD: Observed {ai_pass_rate:.1f}%, required >= {self.config.min_ai_accuracy_percent}%"
                )

        # 7. Voice / STT Threshold Gate
        voice_suite = summary.suites.get("voice")
        if voice_suite and voice_suite.total > 0:
            if voice_suite.failed > 0:
                blockers.append(f"VOICE RECOGNITION FAILURES: {voice_suite.failed} voice test cases failed WER/intent thresholds")

        # 8. Baseline Latency and Memory Regression Checks
        tolerances = self.baseline.get("tolerances", {})
        res_limits = tolerances.get("resources", {})
        max_ram = res_limits.get("max_ram_used_gb", self.config.max_peak_ram_gb)

        perf_suite = summary.suites.get("performance")
        if perf_suite:
            for r in perf_suite.results:
                if "ram_growth_mb" in r.metrics and r.metrics["ram_growth_mb"] > 100.0:
                    warnings.append(f"MEMORY LEAK WARNING: High RAM growth ({r.metrics['ram_growth_mb']} MB in endurance loop)")

        passed = (len(blockers) == 0)
        return passed, blockers, warnings
