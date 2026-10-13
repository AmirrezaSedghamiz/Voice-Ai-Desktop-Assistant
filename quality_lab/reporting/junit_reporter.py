"""
Quality Lab JUnit XML Report Generator.
Generates standard JUnit XML files for conventional automated test reporting and CI/CD ingestion.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from quality_lab.models import RunSummary, TestStatus


def generate_junit_xml_report(summary: RunSummary, output_path: Path) -> Path:
    """Produces JUnit XML document representing the Quality Lab execution."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    testsuites = ET.Element("testsuites", {
        "name": "QualityLab",
        "time": str(summary.duration_seconds),
        "tests": str(summary.total_tests),
        "failures": str(summary.failed),
        "errors": str(summary.error),
    })

    for s_name, s_res in summary.suites.items():
        suite_el = ET.SubElement(testsuites, "testsuite", {
            "name": s_name,
            "tests": str(s_res.total),
            "failures": str(s_res.failed),
            "errors": str(s_res.error),
            "skipped": str(s_res.skipped + s_res.inconclusive),
            "time": str(s_res.duration_seconds),
        })

        for r in s_res.results:
            case_el = ET.SubElement(suite_el, "testcase", {
                "classname": f"quality_lab.{s_name}",
                "name": f"{r.test_id} - {r.name}",
                "time": str(r.duration_seconds),
            })

            if r.status == TestStatus.FAILED:
                fail_el = ET.SubElement(case_el, "failure", {
                    "message": r.diagnostic_message or "Assertion failed",
                    "type": str(r.failure_category.value),
                })
                fail_el.text = f"Expected: {r.expected_outcome}\nObserved: {r.observed_outcome}\nDiagnostic: {r.diagnostic_message}"
            elif r.status == TestStatus.ERROR:
                err_el = ET.SubElement(case_el, "error", {
                    "message": r.diagnostic_message or "Execution error",
                    "type": str(r.failure_category.value),
                })
                err_el.text = r.diagnostic_message
            elif r.status in (TestStatus.SKIPPED, TestStatus.INCONCLUSIVE):
                skip_el = ET.SubElement(case_el, "skipped", {
                    "message": f"Status: {r.status.value}. {r.diagnostic_message}",
                })

    tree = ET.ElementTree(testsuites)
    ET.indent(tree, space="  ", level=0)
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True)
    return output_path
