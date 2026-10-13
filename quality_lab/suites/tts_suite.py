"""
Quality Lab Suite: Text-to-Speech (TTS) and Audio Output Evaluation Suite.
Evaluates local Piper ONNX voice availability, RTL/Unicode handling,
markdown stripping, speech synthesis latency, Real-Time Factor (RTF), and Persian phoneme boundary safety.
"""

from __future__ import annotations

import time
from quality_lab.config import QualityLabConfig
from quality_lab.models import FailureCategory, Severity, SuiteResult, TestMode, TestResult, TestStatus
from src.audio.config import AudioConfig
from src.audio.tts import PiperTtsEngine, SynthesisResult


class TtsSuite:
    """Evaluates local speech synthesis quality, latency, and boundary handling."""

    def __init__(self, config: QualityLabConfig):
        self.config = config

    def run(self) -> SuiteResult:
        suite = SuiteResult(suite_name="tts", status=TestStatus.PASSED)
        cases = [
            self._test_empty_and_whitespace_input,
            self._test_markdown_and_emoji_stripping_contract,
            self._test_persian_phoneme_boundary_handling,
            self._test_english_synthesis_latency_and_rtf,
            self._test_excessively_long_text_synthesis,
            self._test_missing_voice_model_exception,
            self._test_resource_unloading,
        ]

        for case_fn in cases:
            res = case_fn()
            suite.results.append(res)

        suite.recompute_summary()
        return suite

    def _test_empty_and_whitespace_input(self) -> TestResult:
        start_t = time.time()
        test_id = "TTS-EDGE-EMPTY-001"
        name = "TTS Empty and Whitespace Text Handling"
        try:
            cfg = AudioConfig()
            tts = PiperTtsEngine(cfg)
            res = tts.synthesize("    ")

            assert res.audio_data is None
            assert res.text_spoken == ""
            assert res.audio_duration_seconds == 0.0

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="No audio generated for empty/whitespace input",
                observed_outcome="Returned empty SynthesisResult cleanly",
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )

    def _test_markdown_and_emoji_stripping_contract(self) -> TestResult:
        start_t = time.time()
        test_id = "TTS-PURE-STRIP-002"
        name = "TTS Markdown and Emoji Stripping Contract"
        try:
            raw = "Hello!\n[POLICY BLOCK] ignored.\n```python\nprint(1)\n```\nReady to assist 😊."
            sanitized = PiperTtsEngine.sanitize_for_speech(raw)

            assert "[POLICY BLOCK]" not in sanitized
            assert "python" not in sanitized
            assert "😊" not in sanitized
            assert sanitized == "Hello! Ready to assist ."

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Clean spoken string without raw JSON/markdown/emojis",
                observed_outcome=sanitized,
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )

    def _test_persian_phoneme_boundary_handling(self) -> TestResult:
        start_t = time.time()
        test_id = "TTS-LANG-PERSIAN-GUARD-003"
        name = "TTS Persian Language Boundary Guard"
        try:
            cfg = AudioConfig()
            tts = PiperTtsEngine(cfg)

            # Persian text passed to English voice model must return language_supported=False
            res = tts.synthesize("سلام، درخواست شما با موفقیت انجام شد.")
            assert res.language_supported is False
            assert res.audio_data is None

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Persian text detected; English ONNX voice synthesis skipped to avoid corrupt audio",
                observed_outcome="language_supported=False",
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_english_synthesis_latency_and_rtf(self) -> TestResult:
        start_t = time.time()
        test_id = "TTS-ONNX-SYNTH-004"
        name = "Piper ONNX English Speech Synthesis & RTF"

        model_file = self.config.project_root / "models" / "tts" / "en_US-lessac-medium.onnx"
        if not model_file.exists():
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.INCONCLUSIVE,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Piper ONNX synthesizes clean speech buffer",
                observed_outcome="Model file not found on disk",
                failure_category=FailureCategory.UNAVAILABLE_ASSET,
                diagnostic_message=f"Missing model at {model_file}",
                severity=Severity.HIGH,
            )

        try:
            cfg = AudioConfig()
            tts = PiperTtsEngine(cfg)
            tts.load_voice()

            t_synth_start = time.time()
            res = tts.synthesize("Your laptop battery is at one hundred percent and plugged into power.")
            synth_duration = time.time() - t_synth_start

            assert res.audio_data is not None
            assert len(res.audio_data) > 0
            assert res.audio_duration_seconds > 2.0
            assert res.real_time_factor < 0.50  # Must be faster than half real-time

            tts.unload_voice()

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.PASSED,
                mode=TestMode.MODEL,
                duration_seconds=round(synth_duration, 4),
                expected_outcome=f"Audio synthesized with RTF < 0.50 (Observed RTF: {res.real_time_factor:.2f})",
                observed_outcome=f"Duration: {res.audio_duration_seconds:.2f}s | Synthesis: {res.synthesis_time_seconds:.2f}s | RTF: {res.real_time_factor:.2f}",
                metrics={
                    "audio_duration_seconds": res.audio_duration_seconds,
                    "synthesis_time_seconds": res.synthesis_time_seconds,
                    "real_time_factor": res.real_time_factor,
                },
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.FAILED,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_excessively_long_text_synthesis(self) -> TestResult:
        start_t = time.time()
        test_id = "TTS-LONG-TEXT-005"
        name = "TTS Long Text Stability (Paragraph Chunking)"

        model_file = self.config.project_root / "models" / "tts" / "en_US-lessac-medium.onnx"
        if not model_file.exists():
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.INCONCLUSIVE,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Synthesizes long multi-sentence paragraph",
                observed_outcome="Model file not found",
                failure_category=FailureCategory.UNAVAILABLE_ASSET,
                severity=Severity.MEDIUM,
            )

        try:
            cfg = AudioConfig()
            tts = PiperTtsEngine(cfg)
            tts.load_voice()

            long_text = (
                "David is an offline AI assistant. "
                "It manages local tasks and stores facts in SQLite. "
                "All neural models run locally on your hardware without internet."
            )
            res = tts.synthesize(long_text)
            assert res.audio_data is not None
            assert res.audio_duration_seconds > 4.0
            tts.unload_voice()

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.PASSED,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Synthesized 3-sentence utterance without truncation",
                observed_outcome=f"Audio duration: {res.audio_duration_seconds:.2f}s",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.FAILED,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )

    def _test_missing_voice_model_exception(self) -> TestResult:
        start_t = time.time()
        test_id = "TTS-ERR-MISSING-MODEL-006"
        name = "TTS Missing Model Graceful Exception Handling"
        try:
            cfg = AudioConfig(tts_model_path=self.config.project_root / "non_existent_voice.onnx")
            tts = PiperTtsEngine(cfg)
            try:
                tts.load_voice()
                raised = False
            except FileNotFoundError:
                raised = True

            assert raised is True

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="FileNotFoundError raised with actionable download instruction",
                observed_outcome="Exception handled cleanly",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )

    def _test_resource_unloading(self) -> TestResult:
        start_t = time.time()
        test_id = "TTS-LIFECYCLE-UNLOAD-007"
        name = "TTS Voice Model Unload and Memory Release"
        try:
            cfg = AudioConfig()
            tts = PiperTtsEngine(cfg)
            tts.unload_voice()
            assert tts.is_loaded is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Voice released and is_loaded=False",
                observed_outcome="is_loaded=False",
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="tts",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )
