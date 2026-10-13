"""
Quality Lab Core Data Models & Stable Result Schema.
Defines test status, execution mode, failure classification, test-case definitions,
and telemetry structures with strict sensitive-data redaction.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field, field_serializer


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    INCONCLUSIVE = "inconclusive"


class TestMode(str, Enum):
    MOCKED = "mocked"
    INTEGRATION = "integration"
    MODEL = "model"
    HARDWARE = "hardware"
    PACKAGED = "packaged"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureCategory(str, Enum):
    NONE = "none"
    ASSERTION_FAILED = "assertion_failed"
    SECURITY_VIOLATION = "security_violation"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    TIMEOUT = "timeout"
    MISSING_DEPENDENCY = "missing_dependency"
    UNAVAILABLE_ASSET = "unavailable_asset"
    UNAVAILABLE_HARDWARE = "unavailable_hardware"
    MODEL_INFERENCE_ERROR = "model_inference_error"
    CRASH = "crash"
    REGRESSION = "regression"


SENSITIVE_PATTERNS = [
    (re.compile(r"(password|secret|api_key|token|access_token)\s*[:=]\s*['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE), r"\1: [REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"), "[REDACTED_PHONE]"),
]


def redact_sensitive_text(text: str) -> str:
    """Applies privacy redaction to protect sensitive user credentials or PII in test traces."""
    if not text:
        return text
    redacted = str(text)
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class TestCaseDefinition(BaseModel):
    """Specification of a reproducible Quality Lab test case."""

    id: str = Field(description="Unique, stable test case identifier (e.g. AI-FA-001)")
    name: str = Field(description="Human-readable title")
    suite: str = Field(description="Parent test suite name (unit, ai, voice, security, etc.)")
    category: str = Field(description="Functional category (e.g. reasoning, injection, tasks)")
    language: str = Field(default="en", description="Target language ('en', 'fa', 'mixed', or 'na')")
    description: str = Field(default="", description="Detailed intent and behavior description")
    input_data: Any = Field(default=None, description="Input text, audio reference, or mock payload")
    expected_behavior: str = Field(default="", description="Expected outcome description")
    required_permissions: list[str] = Field(default_factory=list, description="Required policy permissions")
    expected_tools: list[str] = Field(default_factory=list, description="Expected tool names if applicable")
    expected_arguments: dict[str, Any] = Field(default_factory=dict, description="Expected parameter constraints")
    evaluation_method: str = Field(default="deterministic", description="deterministic, rubric, or wer")
    severity: Severity = Field(default=Severity.MEDIUM, description="Failure severity")
    requires_hardware: bool = Field(default=False, description="Whether real audio/GPU hardware is required")
    requires_model: bool = Field(default=False, description="Whether real neural model weights are needed")
    is_release_gate: bool = Field(default=True, description="Whether this case gates production releases")


class TestResult(BaseModel):
    """Stable, version-controlled execution result for an individual test case."""

    run_id: str = Field(description="Unique identifier for the test execution run")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 execution timestamp",
    )
    test_id: str = Field(description="Test case identifier")
    name: str = Field(description="Human-readable test name")
    suite: str = Field(description="Suite name")
    status: TestStatus = Field(description="Execution status")
    mode: TestMode = Field(description="Test mode (mocked, integration, model, hardware, packaged)")
    duration_seconds: float = Field(ge=0.0, description="Elapsed execution time in seconds")
    expected_outcome: str = Field(default="", description="Redacted expected outcome")
    observed_outcome: str = Field(default="", description="Redacted observed outcome")
    failure_category: FailureCategory = Field(default=FailureCategory.NONE)
    diagnostic_message: str = Field(default="", description="Detailed error trace or reasoning")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Numerical measurements (WER, TTFT, TPS, etc.)")
    environment_metadata: dict[str, Any] = Field(default_factory=dict, description="Host environment metadata")
    sensitive_data_redacted: bool = Field(default=True, description="Flag confirming sensitive data filtering")
    severity: Severity = Field(default=Severity.MEDIUM)
    is_release_gate: bool = Field(default=True)

    @field_serializer("expected_outcome", "observed_outcome", "diagnostic_message")
    def serialize_redacted_text(self, v: str) -> str:
        return redact_sensitive_text(v)


class SuiteResult(BaseModel):
    """Aggregated outcome of an individual test suite."""

    suite_name: str
    status: TestStatus
    duration_seconds: float = 0.0
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    inconclusive: int = 0
    results: list[TestResult] = Field(default_factory=list)

    def recompute_summary(self) -> None:
        self.total = len(self.results)
        self.passed = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        self.failed = sum(1 for r in self.results if r.status == TestStatus.FAILED)
        self.skipped = sum(1 for r in self.results if r.status == TestStatus.SKIPPED)
        self.error = sum(1 for r in self.results if r.status == TestStatus.ERROR)
        self.inconclusive = sum(1 for r in self.results if r.status == TestStatus.INCONCLUSIVE)
        self.duration_seconds = round(sum(r.duration_seconds for r in self.results), 3)

        if self.failed > 0 or self.error > 0:
            self.status = TestStatus.FAILED
        elif self.inconclusive > 0:
            self.status = TestStatus.INCONCLUSIVE
        elif self.skipped == self.total and self.total > 0:
            self.status = TestStatus.SKIPPED
        else:
            self.status = TestStatus.PASSED


class RunSummary(BaseModel):
    """Top-level Quality Lab execution summary."""

    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_seconds: float = 0.0
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    inconclusive: int = 0
    suites: dict[str, SuiteResult] = Field(default_factory=dict)
    release_gate_passed: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    environment_telemetry: dict[str, Any] = Field(default_factory=dict)
    model_metadata: dict[str, Any] = Field(default_factory=dict)

    def recompute(self) -> None:
        self.total_tests = sum(s.total for s in self.suites.values())
        self.passed = sum(s.passed for s in self.suites.values())
        self.failed = sum(s.failed for s in self.suites.values())
        self.skipped = sum(s.skipped for s in self.suites.values())
        self.error = sum(s.error for s in self.suites.values())
        self.inconclusive = sum(s.inconclusive for s in self.suites.values())
        self.duration_seconds = round(sum(s.duration_seconds for s in self.suites.values()), 3)
