"""
Quality Lab Command-Line Interface (CLI).
Provides entry point for running suites, viewing reports, and comparing runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quality_lab.config import QualityLabConfig, get_default_lab_config
from quality_lab.orchestrator import QualityLabOrchestrator
from quality_lab.registry import list_available_suites
from quality_lab.reporting.comparator import compare_runs_with_baseline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m quality_lab",
        description="David Local Windows AI Assistant - Quality Lab Testing System",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. list
    list_parser = subparsers.add_parser("list", help="List available test suites and datasets")

    # 2. run
    run_parser = subparsers.add_parser("run", help="Execute one or more Quality Lab suites")
    run_parser.add_argument(
        "--suite",
        "-s",
        type=str,
        default="all",
        help="Suite name to run: unit, integration, ai, voice, wake_word, tts, security, performance, gui, packaged, release, or all (default: all)",
    )
    run_parser.add_argument(
        "--hardware",
        action="store_true",
        help="Enable live audio device and physical GPU execution tests",
    )
    run_parser.add_argument(
        "--heavy-models",
        action="store_true",
        help="Enable loading the full 1.7B LLM or neural weights during testing",
    )
    run_parser.add_argument(
        "--exe",
        type=str,
        help="Path to the packaged Windows executable for packaged suite validation",
    )
    run_parser.add_argument(
        "--filter",
        "-f",
        type=str,
        help="Filter test cases by ID or name substring",
    )
    run_parser.add_argument(
        "--lang",
        choices=["en", "fa", "mixed", "all"],
        default="all",
        help="Filter AI or Voice test cases by language",
    )
    run_parser.add_argument(
        "--severity",
        choices=["low", "medium", "high", "critical", "all"],
        default="all",
        help="Filter test cases by severity level",
    )

    # 3. report
    report_parser = subparsers.add_parser("report", help="Display or locate generated test reports")
    report_parser.add_argument(
        "--latest",
        action="store_true",
        help="Display the most recent Quality Lab run summary",
    )
    report_parser.add_argument(
        "--run-id",
        type=str,
        help="Display summary for a specific run ID",
    )

    # 4. compare
    compare_parser = subparsers.add_parser("compare", help="Compare a run against a baseline or historical run")
    compare_parser.add_argument(
        "--baseline",
        "-b",
        type=str,
        help="Baseline specification file or historical run ID to compare against",
    )
    compare_parser.add_argument(
        "--current",
        "-c",
        type=str,
        help="Current run ID or summary file (defaults to latest)",
    )

    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    config = get_default_lab_config()

    if parsed.command == "list":
        print("\n=== David Assistant Quality Lab - Registered Suites ===")
        suites = list_available_suites()
        for s in suites:
            print(f"  - {s}")
        print("\nComposite Targets:")
        print("  - release    (Executes all required release-gating suites)")
        print("  - all        (Executes all registered suites)")
        print()
        return 0

    elif parsed.command == "run":
        if parsed.hardware:
            config.allow_hardware = True
        if parsed.heavy_models:
            config.allow_heavy_models = True
        if parsed.exe:
            config.exe_path = Path(parsed.exe).resolve()

        orchestrator = QualityLabOrchestrator(config)
        summary = orchestrator.run_suites(
            suites=parsed.suite,
            filter_pattern=parsed.filter,
            language_filter=None if parsed.lang == "all" else parsed.lang,
            severity_filter=None if parsed.severity == "all" else parsed.severity,
        )

        # Distinguish exit codes
        if summary.failed > 0 or summary.error > 0:
            return 1
        if not summary.release_gate_passed:
            return 1
        if summary.inconclusive > 0:
            return 3
        return 0

    elif parsed.command == "report":
        rep_dir = config.reports_dir
        target_file = None
        if parsed.latest or not parsed.run_id:
            target_file = rep_dir / "latest_summary.json"
        else:
            target_file = rep_dir / f"{parsed.run_id}.json"

        if not target_file.exists():
            print(f"[!] No report found at {target_file}", file=sys.stderr)
            return 2

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"\n=== Quality Lab Report: {data.get('run_id')} ===")
        print(f"Timestamp:   {data.get('timestamp')}")
        print(f"Duration:    {data.get('duration_seconds')}s")
        print(f"Total Tests: {data.get('total_tests')} | Passed: {data.get('passed')} | Failed: {data.get('failed')} | Inconclusive: {data.get('inconclusive')}")
        gate = "PASSED" if data.get('release_gate_passed') else "FAILED"
        print(f"Release Gate:{gate}")
        if data.get('blockers'):
            print(f"\nBlockers ({len(data['blockers'])}):")
            for b in data['blockers']:
                print(f"  - {b}")
        print(f"\nHTML Report: file:///{rep_dir / (data.get('run_id') + '.html')}\n")
        return 0

    elif parsed.command == "compare":
        rep_dir = config.reports_dir
        # Determine current run
        curr_path = rep_dir / "latest_summary.json"
        if parsed.current:
            if Path(parsed.current).exists():
                curr_path = Path(parsed.current)
            else:
                curr_path = rep_dir / f"{parsed.current}.json"

        if not curr_path.exists():
            print(f"[!] Current summary file not found at {curr_path}", file=sys.stderr)
            return 2

        with open(curr_path, "r", encoding="utf-8") as f:
            curr_data = json.load(f)

        from quality_lab.models import RunSummary
        curr_summary = RunSummary.model_validate(curr_data)

        # Baseline
        base_path = config.baselines_dir / "default_baseline.json"
        if parsed.baseline:
            if Path(parsed.baseline).exists():
                base_path = Path(parsed.baseline)
            else:
                base_path = rep_dir / f"{parsed.baseline}.json"

        diff = compare_runs_with_baseline(curr_summary, base_path)
        print(f"\n=== Regression Comparison Result: [{diff['verdict']}] ===")
        print(f"Run ID:             {diff.get('run_id')}")
        print(f"Total Regressions:  {diff.get('total_regressions')}")
        print(f"Total Improvements: {diff.get('total_improvements')}")

        if diff.get("regressions"):
            print("\n[!] REGRESSIONS DETECTED:")
            for r in diff["regressions"]:
                print(f"  - [{r.get('category')}] {r.get('description')}")

        if diff.get("improvements"):
            print("\n[+] IMPROVEMENTS:")
            for imp in diff["improvements"]:
                print(f"  - [{imp.get('category')}] {imp.get('test_id')} now passing")

        print("=========================================================\n")
        return 1 if diff["total_regressions"] > 0 else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
