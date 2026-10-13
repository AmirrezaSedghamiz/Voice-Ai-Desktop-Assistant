"""
Quality Lab Central Orchestrator.
Discovers hardware capabilities, coordinates execution of individual or composite test suites,
enforces release gating policies, and generates multi-format reports.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from quality_lab.baselines import load_default_baseline
from quality_lab.config import QualityLabConfig, get_default_lab_config
from quality_lab.hardware import detect_hardware_capabilities
from quality_lab.models import RunSummary, TestStatus
from quality_lab.registry import AVAILABLE_SUITES, get_suite_instance, list_available_suites
from quality_lab.reporting.html_reporter import generate_html_report
from quality_lab.reporting.json_reporter import generate_json_report
from quality_lab.reporting.junit_reporter import generate_junit_xml_report
from quality_lab.suites.release_gate import ReleaseGateEvaluator


class QualityLabOrchestrator:
    """Master controller executing Quality Lab suites and generating artifacts."""

    def __init__(self, config: QualityLabConfig | None = None):
        self.config = config or get_default_lab_config()
        self.hardware_caps = detect_hardware_capabilities(self.config.project_root)
        self.baseline = load_default_baseline()
        self.release_evaluator = ReleaseGateEvaluator(self.config, baseline=self.baseline)

    def run_suites(
        self,
        suites: list[str] | str = "all",
        filter_pattern: Optional[str] = None,
        language_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
    ) -> RunSummary:
        """
        Runs the specified test suites and returns the aggregated RunSummary.
        'all' or 'release' executes all production release suites.
        """
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        if isinstance(suites, str):
            if suites.lower() in ("all", "release"):
                target_suites = list_available_suites()
            else:
                target_suites = [s.strip().lower() for s in suites.split(",")]
        else:
            target_suites = [s.lower() for s in suites]

        summary = RunSummary(
            run_id=run_id,
            environment_telemetry=self.hardware_caps.model_dump(mode="json"),
        )

        print(f"\n=================================================================")
        print(f"       DAVID QUALITY LAB EXECUTION RUN ({run_id})")
        print(f"=================================================================")
        print(f"  Target Suites:    {', '.join(target_suites)}")
        print(f"  Allow Hardware:   {self.config.allow_hardware}")
        print(f"  Allow Heavy Model:{self.config.allow_heavy_models}")
        print(f"  Host Environment: Windows {self.hardware_caps.os_release} ({self.hardware_caps.architecture})")
        print(f"  Cores / RAM:      {self.hardware_caps.cpu_count_logical} vCPUs | {self.hardware_caps.total_ram_gb} GB RAM")
        if self.hardware_caps.gpu_available:
            print(f"  GPU / VRAM:       {self.hardware_caps.gpu_name} ({self.hardware_caps.gpu_vram_total_mb:.0f} MB)")
        print(f"=================================================================\n")

        for s_name in target_suites:
            if s_name not in AVAILABLE_SUITES:
                print(f"[!] Warning: Suite '{s_name}' is not recognized. Skipping.")
                continue

            print(f"[*] Running suite: [{s_name.upper()}] ...", end="", flush=True)
            suite_start = time.time()
            try:
                suite_instance = get_suite_instance(s_name, self.config)
                suite_result = suite_instance.run()

                # Optional filtering
                if filter_pattern or language_filter or severity_filter:
                    filtered_results = []
                    for r in suite_result.results:
                        if filter_pattern and filter_pattern.lower() not in (r.test_id + r.name).lower():
                            continue
                        filtered_results.append(r)
                    suite_result.results = filtered_results
                    suite_result.recompute_summary()

                summary.suites[s_name] = suite_result
                duration = time.time() - suite_start
                status_badge = suite_result.status.value.upper()
                print(f" Done ({duration:.2f}s) -> {status_badge} ({suite_result.passed}/{suite_result.total} passed)")

            except Exception as e:
                import traceback
                diag = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                print(f" ERROR: {diag}")
                traceback.print_exc()

        # Recalculate summary totals
        summary.recompute()

        # Evaluate Release Gate
        passed, blockers, warnings = self.release_evaluator.evaluate(summary)
        summary.release_gate_passed = passed
        summary.blockers = blockers
        summary.warnings = warnings

        # Save artifacts to reports directory
        self._save_reports(summary)

        self._print_run_summary(summary)
        return summary

    def _save_reports(self, summary: RunSummary) -> None:
        """Serializes JSON, HTML, JUnit XML reports and updates latest report pointer."""
        rep_dir = self.config.reports_dir
        rep_dir.mkdir(parents=True, exist_ok=True)

        json_path = rep_dir / f"{summary.run_id}.json"
        html_path = rep_dir / f"{summary.run_id}.html"
        junit_path = rep_dir / f"{summary.run_id}.junit.xml"

        generate_json_report(summary, json_path)
        generate_html_report(summary, html_path)
        generate_junit_xml_report(summary, junit_path)

        # Save latest reference
        latest_json = rep_dir / "latest_summary.json"
        generate_json_report(summary, latest_json)

    def _print_run_summary(self, summary: RunSummary) -> None:
        """Prints a human-readable terminal summary table."""
        print(f"\n=================================================================")
        print(f"                     QUALITY LAB RUN SUMMARY                     ")
        print(f"=================================================================")
        print(f"{'SUITE':<16} | {'STATUS':<12} | {'PASS':<6} | {'FAIL':<6} | {'TIME(s)':<8}")
        print("-" * 65)

        for s_name, s_res in summary.suites.items():
            print(
                f"{s_name:<16} | {s_res.status.value.upper():<12} | "
                f"{s_res.passed:<6} | {s_res.failed:<6} | {s_res.duration_seconds:<8.2f}"
            )

        print("-" * 65)
        print(
            f"TOTAL TESTS: {summary.total_tests:<4} | PASSED: {summary.passed:<4} | "
            f"FAILED: {summary.failed:<4} | TIME: {summary.duration_seconds:.2f}s"
        )

        if summary.blockers:
            print(f"\n[!] RELEASE BLOCKERS ({len(summary.blockers)}):")
            for b in summary.blockers:
                print(f"  - {b}")

        if summary.warnings:
            print(f"\n[*] RELEASE WARNINGS ({len(summary.warnings)}):")
            for w in summary.warnings:
                print(f"  - {w}")

        gate_verdict = "PASS" if summary.release_gate_passed else "FAIL"
        print(f"\nRELEASE GATE DECISION: [{gate_verdict}]")
        print(f"HTML Report: file:///{self.config.reports_dir / (summary.run_id + '.html')}")
        print(f"JSON Report: file:///{self.config.reports_dir / (summary.run_id + '.json')}")
        print(f"JUnit XML:   file:///{self.config.reports_dir / (summary.run_id + '.junit.xml')}")
        print("=================================================================\n")
