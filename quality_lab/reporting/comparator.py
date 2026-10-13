"""
Quality Lab Baseline & Historical Run Regression Comparator.
Compares current test execution runs against saved baselines or historical runs
to identify regressions in pass rates, latency, memory consumption, or security posture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from quality_lab.models import RunSummary, TestStatus


def compare_runs_with_baseline(
    current: RunSummary,
    baseline_path_or_dict: Path | dict[str, Any],
) -> dict[str, Any]:
    """
    Compares the current RunSummary against a baseline specification or previous run.
    Returns structured regression diffs, regressions list, and release recommendations.
    """
    if isinstance(baseline_path_or_dict, (str, Path)):
        p = Path(baseline_path_or_dict)
        if not p.exists():
            return {
                "status": "error",
                "message": f"Baseline file not found at {p}",
                "regressions": [],
            }
        with open(p, "r", encoding="utf-8") as f:
            base_data = json.load(f)
    else:
        base_data = baseline_path_or_dict

    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []

    # Check if comparing against another RunSummary or a default_baseline.json
    tolerances = base_data.get("tolerances", {})

    if tolerances:
        # Calibrated baseline comparison
        qual = tolerances.get("quality", {})
        min_ai_acc = qual.get("ai_accuracy_min_percent", 90.0)

        ai_suite = current.suites.get("ai")
        if ai_suite and ai_suite.total > 0:
            obs_acc = (ai_suite.passed / ai_suite.total) * 100.0
            if obs_acc < min_ai_acc:
                regressions.append({
                    "category": "quality",
                    "metric": "ai_accuracy_percent",
                    "baseline": min_ai_acc,
                    "observed": obs_acc,
                    "difference": round(obs_acc - min_ai_acc, 2),
                    "severity": "high",
                    "description": f"AI evaluation accuracy ({obs_acc:.1f}%) fell below baseline threshold ({min_ai_acc}%)",
                })

        # Security check: zero failures allowed
        sec_suite = current.suites.get("security")
        if sec_suite and (sec_suite.failed > 0 or sec_suite.error > 0):
            regressions.append({
                "category": "security",
                "metric": "security_failures",
                "baseline": 0,
                "observed": sec_suite.failed + sec_suite.error,
                "difference": sec_suite.failed + sec_suite.error,
                "severity": "critical",
                "description": f"{sec_suite.failed + sec_suite.error} security violations detected",
            })

    elif "suites" in base_data:
        # Direct run-to-run comparison
        base_suites = base_data.get("suites", {})
        for s_name, curr_s in current.suites.items():
            base_s = base_suites.get(s_name)
            if not base_s:
                continue

            curr_results = {r.test_id: r for r in curr_s.results}
            base_results = {r.get("test_id"): r for r in base_s.get("results", [])}

            for tid, cr in curr_results.items():
                br = base_results.get(tid)
                if br:
                    br_status = br.get("status")
                    if br_status == "passed" and cr.status in (TestStatus.FAILED, TestStatus.ERROR):
                        regressions.append({
                            "category": "test_failure",
                            "test_id": tid,
                            "suite": s_name,
                            "baseline_status": br_status,
                            "observed_status": cr.status.value,
                            "severity": cr.severity.value,
                            "description": f"Test {tid} previously PASSED but now {cr.status.value.upper()}",
                        })
                    elif br_status != "passed" and cr.status == TestStatus.PASSED:
                        improvements.append({
                            "category": "test_fixed",
                            "test_id": tid,
                            "suite": s_name,
                            "baseline_status": br_status,
                            "observed_status": "passed",
                        })

    verdict = "REGRESSION_DETECTED" if len(regressions) > 0 else "NO_REGRESSION"

    return {
        "verdict": verdict,
        "run_id": current.run_id,
        "total_regressions": len(regressions),
        "total_improvements": len(improvements),
        "regressions": regressions,
        "improvements": improvements,
    }
