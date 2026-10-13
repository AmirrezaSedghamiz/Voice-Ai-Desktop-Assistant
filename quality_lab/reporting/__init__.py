"""
Quality Lab Multi-Format Reporting & Regression Analysis Package.
Provides HTML, JSON, JUnit XML generation, and baseline regression comparison.
"""

from quality_lab.reporting.comparator import compare_runs_with_baseline
from quality_lab.reporting.html_reporter import generate_html_report
from quality_lab.reporting.json_reporter import generate_json_report
from quality_lab.reporting.junit_reporter import generate_junit_xml_report

__all__ = [
    "compare_runs_with_baseline",
    "generate_html_report",
    "generate_json_report",
    "generate_junit_xml_report",
]
