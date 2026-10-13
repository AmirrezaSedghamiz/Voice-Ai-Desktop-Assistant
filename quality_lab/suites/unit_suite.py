"""
Quality Lab Suite: Unit and Contract Tests.
Tests critical pure functions, schemas, configuration validation, policy boundaries,
state transitions, and interface contracts without external dependencies or hardware.
"""

from __future__ import annotations

import time
import pytest
from pydantic import ValidationError

from quality_lab.config import QualityLabConfig
from quality_lab.models import FailureCategory, Severity, SuiteResult, TestMode, TestResult, TestStatus
from src.agent.orchestrator import extract_name_from_user_text, strip_emojis
from src.agent.policy_engine import PolicyEngine
from src.agent.tools.models import ExecutionStatus, RiskLevel, ToolDefinition, ToolResult
from src.agent.tools.registry import ToolRegistry
from src.audio.tts import PiperTtsEngine
from src.core.config import AssistantSettings, NetworkIsolationConfig, ResourceGovernorConfig
from src.memory.store import normalize_fact_key
from src.ui.config import UiConfig


class UnitSuite:
    """Executes fast, deterministic unit and contract tests."""

    def __init__(self, config: QualityLabConfig):
        self.config = config

    def run(self) -> SuiteResult:
        suite = SuiteResult(suite_name="unit", status=TestStatus.PASSED)
        cases = [
            self._test_emoji_stripping,
            self._test_name_extraction_en_and_fa,
            self._test_fact_key_normalization,
            self._test_network_isolation_security_contract,
            self._test_resource_governor_validation_contract,
            self._test_policy_engine_allowlist_contract,
            self._test_tool_definition_and_registry_contract,
            self._test_tts_text_sanitization,
            self._test_persian_script_detection,
            self._test_ui_config_defaults,
        ]

        for case_fn in cases:
            res = case_fn()
            suite.results.append(res)

        suite.recompute_summary()
        return suite

    def _test_emoji_stripping(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-PURE-EMOJI-001"
        name = "Emoji Stripping Pure Function"
        try:
            sample = "Hello David! 😊🚀 Working hard? 🎯"
            cleaned = strip_emojis(sample)
            assert cleaned == "Hello David! Working hard?"
            assert strip_emojis("") == ""
            assert strip_emojis(None) == ""
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="All Unicode emojis stripped from string",
                observed_outcome=cleaned,
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )

    def _test_name_extraction_en_and_fa(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-PURE-NAME-002"
        name = "Identity and Name Extraction (English & Persian)"
        try:
            assert extract_name_from_user_text("My name is Amirreza") == "Amirreza"
            assert extract_name_from_user_text("You can call me David.") == "David"
            assert extract_name_from_user_text("اسم من علی است") == "علی"
            assert extract_name_from_user_text("اسمم سارا هست") == "سارا"
            # Identity questions must NOT extract a name
            assert extract_name_from_user_text("اسم من چیه؟") is None
            assert extract_name_from_user_text("What is my name?") is None
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Extracted names in both languages; ignored identity questions",
                observed_outcome="English and Persian regex patterns verified",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )

    def _test_fact_key_normalization(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-PURE-NORM-003"
        name = "Fact Key Normalization"
        try:
            assert normalize_fact_key("  User Preferred Name  ") == "user_preferred_name"
            assert normalize_fact_key("Coffee---Preference!!") == "coffee_preference"
            assert normalize_fact_key("نام_کاربر") == "نام_کاربر"
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Keys normalized to lower snake_case",
                observed_outcome="Valid snake_case strings produced",
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )

    def _test_network_isolation_security_contract(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-CONTRACT-NET-004"
        name = "Network Isolation Strict Boundary Contract"
        try:
            # 1. Non-loopback server host must raise ValueError
            with pytest.raises(ValueError, match="Security Violation"):
                NetworkIsolationConfig(server_host="192.168.1.10")

            with pytest.raises(ValueError, match="Security Violation"):
                NetworkIsolationConfig(server_host="8.8.8.8")

            # 2. allow_external_networking=True must raise ValueError
            with pytest.raises(ValueError, match="External networking is prohibited"):
                NetworkIsolationConfig(allow_external_networking=True)

            # 3. Valid loopback must pass
            valid = NetworkIsolationConfig(server_host="127.0.0.1", allow_external_networking=False)
            assert valid.server_host == "127.0.0.1"

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Rejected external host & network configuration",
                observed_outcome="Security ValueError raised on all violations",
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.SECURITY_VIOLATION,
                diagnostic_message=str(e),
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )

    def _test_resource_governor_validation_contract(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-CONTRACT-GOV-005"
        name = "Resource Governor Bounds Validation Contract"
        try:
            # CPU threads out of bounds
            with pytest.raises(ValidationError):
                ResourceGovernorConfig(cpu_threads=0)
            with pytest.raises(ValidationError):
                ResourceGovernorConfig(cpu_threads=32)

            # Context tokens bounds
            with pytest.raises(ValidationError):
                ResourceGovernorConfig(max_context_tokens=100)

            # Valid defaults
            gov = ResourceGovernorConfig(cpu_threads=4, gpu_layers=24)
            assert gov.process_priority == "BELOW_NORMAL"
            assert gov.idle_timeout_seconds == 300

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Bounds enforced by Pydantic validator",
                observed_outcome="Invalid configurations rejected",
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_policy_engine_allowlist_contract(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-CONTRACT-POLICY-006"
        name = "Policy Engine Tool Allowlist Contract"
        try:
            engine = PolicyEngine()
            # Dangerous actions must be rejected
            for bad_action in ["execute_shell", "execute_cmd", "run_terminal_command", "powershell_script", "raw_sql"]:
                dec = engine.evaluate(bad_action)
                assert dec.allowed is False
                assert dec.risk_level == "admin_denied"

            # Whitelisted actions must be permitted
            for good_action in ["get_battery_status", "get_system_status", "create_task"]:
                dec = engine.evaluate(good_action)
                assert dec.allowed is True

            # Unregistered tool must be rejected
            dec = engine.evaluate("unregistered_hack_tool")
            assert dec.allowed is False
            assert dec.risk_level == "unregistered"

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Dangerous & unregistered tools blocked; whitelisted tools allowed",
                observed_outcome="Policy decisions verified",
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.SECURITY_VIOLATION,
                diagnostic_message=str(e),
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )

    def _test_tool_definition_and_registry_contract(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-CONTRACT-REGISTRY-007"
        name = "Tool Definition and Registry Contract"
        try:
            reg = ToolRegistry()
            t = ToolDefinition(
                name="test_tool",
                description="Test handler",
                risk_level=RiskLevel.SAFE_READ,
                handler=lambda: ToolResult(success=True, result={"val": 1}),
            )
            reg.register(t)
            assert reg.has_tool("test_tool")

            # Duplicate registration should raise error
            with pytest.raises(ValueError, match="already registered"):
                reg.register(t)

            retrieved = reg.get_tool("test_tool")
            assert retrieved is not None
            assert retrieved.name == "test_tool"

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Registry manages tools and prevents duplicates",
                observed_outcome="Tool registered and verified",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            diag = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=diag,
                severity=Severity.MEDIUM,
            )

    def _test_tts_text_sanitization(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-PURE-TTS-SANITIZE-008"
        name = "TTS Speech Sanitization Contract"
        try:
            raw = (
                "[Tool Output (get_battery_status)]: Battery 100%\n"
                "```python\nprint(1)\n```\n"
                "Ready to assist 😊."
            )
            sanitized = PiperTtsEngine.sanitize_for_speech(raw)
            assert "[Tool Output" not in sanitized
            assert "print(1)" not in sanitized
            assert "python" not in sanitized
            assert "😊" not in sanitized
            assert sanitized == "Ready to assist ."

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Markup, code blocks, emojis, and tool traces stripped for speech",
                observed_outcome=sanitized,
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            diag = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=diag,
                severity=Severity.MEDIUM,
            )

    def _test_persian_script_detection(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-PURE-FA-DETECT-009"
        name = "Persian Language Detection Pure Function"
        try:
            assert PiperTtsEngine.is_persian_text("سلام، حال شما چطوره؟") is True
            assert PiperTtsEngine.is_persian_text("یک تسک جدید برای فردا بساز") is True
            assert PiperTtsEngine.is_persian_text("Hello, how are you?") is False
            assert PiperTtsEngine.is_persian_text("Open notepad") is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Accurately distinguishes Persian script from Latin",
                observed_outcome="Persian and English test strings classified correctly",
                severity=Severity.LOW,
            )
        except Exception as e:
            diag = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=diag,
                severity=Severity.LOW,
            )

    def _test_ui_config_defaults(self) -> TestResult:
        start_t = time.time()
        test_id = "UNIT-MODEL-UI-CFG-010"
        name = "UI Configuration Model Defaults"
        try:
            cfg = UiConfig()
            assert cfg.assistant_name == "David"
            assert cfg.wake_phrase == "activate david"
            assert cfg.trigger_mode in ("ptt", "vad")
            assert cfg.wake_word_enabled is True
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="UIConfig initialized with valid desktop defaults",
                observed_outcome="Valid UIConfig instance",
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="unit",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )
