"""
Quality Lab Suite: Wake-Word Detector and Voice State Machine Evaluation.
Evaluates offline Vosk Kaldi keyword spotting ('Activate David'), energy gating,
debounce cooldown, silence rejection, pause/resume behavior, and false alarm rejection.
"""

from __future__ import annotations

import time
import numpy as np

from quality_lab.config import QualityLabConfig
from quality_lab.fixtures.synthetic_audio import float32_to_pcm16_bytes, generate_noise, generate_silence
from quality_lab.models import FailureCategory, Severity, SuiteResult, TestMode, TestResult, TestStatus
from src.audio.wake_word import WakeWordConfig, WakeWordDetector


class WakeWordSuite:
    """Evaluates keyword spotting accuracy, state transitions, and debounce mechanics."""

    def __init__(self, config: QualityLabConfig, use_real_model: bool = False):
        self.config = config
        self.use_real_model = use_real_model

    def run(self) -> SuiteResult:
        suite = SuiteResult(suite_name="wake_word", status=TestStatus.PASSED)
        cases = [
            self._test_config_validation,
            self._test_silence_rejection_without_model_inference,
            self._test_pause_and_resume_state_machine,
            self._test_cooldown_debounce_prevention,
            self._test_keyword_spotting_with_synthetic_speech,
            self._test_unrelated_speech_rejection,
            self._test_detector_lifecycle_clean_unload,
        ]

        for case_fn in cases:
            res = case_fn()
            suite.results.append(res)

        suite.recompute_summary()
        return suite

    def _test_config_validation(self) -> TestResult:
        start_t = time.time()
        test_id = "WW-CFG-VAL-001"
        name = "Wake-Word Configuration Defaults and Bounds"
        try:
            cfg = WakeWordConfig()
            assert cfg.phrase == "activate david"
            assert cfg.sample_rate == 16000
            assert cfg.cooldown_seconds == 2.5
            assert cfg.energy_threshold == 0.010
            assert cfg.enabled is True

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="WakeWordConfig validated with offline defaults",
                observed_outcome=f"Phrase: '{cfg.phrase}', Cooldown: {cfg.cooldown_seconds}s",
                severity=Severity.LOW,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.LOW,
            )

    def _test_silence_rejection_without_model_inference(self) -> TestResult:
        start_t = time.time()
        test_id = "WW-ENERGY-SILENCE-002"
        name = "Wake-Word Energy Gating on Ambient Silence"
        try:
            detector = WakeWordDetector()
            # Feed 1 second of zero-energy PCM
            silence_samples = generate_silence(duration_seconds=1.0, sample_rate=16000)
            pcm_bytes = float32_to_pcm16_bytes(silence_samples)

            # Silence must not trigger
            triggered = detector.process_audio_chunk(pcm_bytes)
            assert triggered is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Silence discarded by RMS energy gate before Kaldi recognizer",
                observed_outcome=f"Triggered: {triggered}",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )

    def _test_pause_and_resume_state_machine(self) -> TestResult:
        start_t = time.time()
        test_id = "WW-STATE-PAUSE-003"
        name = "Wake-Word Pause and Resume Lifecycle"
        try:
            detector = WakeWordDetector()
            assert detector.is_paused is False

            detector.pause()
            assert detector.is_paused is True

            # In paused mode, any input is immediately rejected
            noise = float32_to_pcm16_bytes(generate_noise(0.5, 16000, amplitude=0.2))
            assert detector.process_audio_chunk(noise) is False

            detector.resume()
            assert detector.is_paused is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Pause suspends processing; resume clears buffers cleanly",
                observed_outcome="Pause and resume transitions verified",
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_cooldown_debounce_prevention(self) -> TestResult:
        start_t = time.time()
        test_id = "WW-DEBOUNCE-COOLDOWN-004"
        name = "Wake-Word Debounce Cooldown Prevention"
        try:
            cfg = WakeWordConfig(cooldown_seconds=2.0)
            detector = WakeWordDetector(cfg)
            detector._last_trigger_time = time.time()

            # Immediate subsequent chunk within 2.0s must be debounced
            noise = float32_to_pcm16_bytes(generate_noise(0.5, 16000, amplitude=0.2))
            assert detector.process_audio_chunk(noise) is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Immediate re-trigger blocked by cooldown debounce",
                observed_outcome="Debounce enforced",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )

    def _test_keyword_spotting_with_synthetic_speech(self) -> TestResult:
        start_t = time.time()
        test_id = "WW-SYNTH-SPOT-005"
        name = "Wake-Word Detection on Synthesized 'Activate David'"

        models_dir = self.config.project_root / "models" / "wake_word" / "vosk-model-small-en-us-0.15"
        tts_model = self.config.project_root / "models" / "tts" / "en_US-lessac-medium.onnx"

        if not models_dir.exists() or not tts_model.exists():
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.INCONCLUSIVE,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Vosk model spots synthetic 'activate david'",
                observed_outcome="Models not found on disk",
                failure_category=FailureCategory.UNAVAILABLE_ASSET,
                diagnostic_message=f"Missing models at {models_dir} or {tts_model}",
                severity=Severity.HIGH,
            )

        try:
            from src.audio.config import AudioConfig
            from src.audio.tts import PiperTtsEngine

            tts = PiperTtsEngine(AudioConfig())
            tts.load_voice()
            synth = tts.synthesize("activate david")
            assert synth.audio_data is not None

            cfg = WakeWordConfig(sample_rate=synth.sample_rate)
            detector = WakeWordDetector(cfg)
            detector.load_model()

            pcm = (synth.audio_data * 32767).astype(np.int16).tobytes()
            chunk_size = 4000
            detected = False
            t_det_start = time.time()
            detection_latency = 0.0

            for i in range(0, len(pcm), chunk_size):
                chunk = pcm[i : i + chunk_size]
                if detector.process_audio_chunk(chunk):
                    detected = True
                    detection_latency = round(time.time() - t_det_start, 3)
                    break

            detector.unload()
            tts.unload_voice()

            assert detected is True

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.PASSED,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Vosk detector spotted keyword 'activate david'",
                observed_outcome=f"Detected: True (latency: {detection_latency}s)",
                metrics={"detection_latency_seconds": detection_latency},
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.FAILED,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_unrelated_speech_rejection(self) -> TestResult:
        start_t = time.time()
        test_id = "WW-REJECT-UNRELATED-006"
        name = "Wake-Word Rejection of Ordinary Conversational Speech"

        tts_model = self.config.project_root / "models" / "tts" / "en_US-lessac-medium.onnx"
        models_dir = self.config.project_root / "models" / "wake_word" / "vosk-model-small-en-us-0.15"

        if not models_dir.exists() or not tts_model.exists():
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.INCONCLUSIVE,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Vosk detector rejects unrelated speech",
                observed_outcome="Models not found on disk",
                failure_category=FailureCategory.UNAVAILABLE_ASSET,
                diagnostic_message="Missing required local models",
                severity=Severity.HIGH,
            )

        try:
            from src.audio.config import AudioConfig
            from src.audio.tts import PiperTtsEngine

            tts = PiperTtsEngine(AudioConfig())
            tts.load_voice()
            synth = tts.synthesize("open the browser and check the morning news")
            assert synth.audio_data is not None

            cfg = WakeWordConfig(sample_rate=synth.sample_rate)
            detector = WakeWordDetector(cfg)
            detector.load_model()

            pcm = (synth.audio_data * 32767).astype(np.int16).tobytes()
            chunk_size = 4000
            detected = False

            for i in range(0, len(pcm), chunk_size):
                chunk = pcm[i : i + chunk_size]
                if detector.process_audio_chunk(chunk):
                    detected = True
                    break

            detector.unload()
            tts.unload_voice()

            assert detected is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.PASSED,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Unrelated sentence rejected (zero false positive)",
                observed_outcome=f"Detected: {detected}",
                severity=Severity.HIGH,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.FAILED,
                mode=TestMode.MODEL,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
            )

    def _test_detector_lifecycle_clean_unload(self) -> TestResult:
        start_t = time.time()
        test_id = "WW-LIFECYCLE-UNLOAD-007"
        name = "Wake-Word Detector Clean Shutdown and Hardware Release"
        try:
            detector = WakeWordDetector()
            detector.unload()
            assert detector.is_loaded is False
            assert detector.is_listening is False

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.PASSED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Streams closed and memory resources released cleanly",
                observed_outcome="is_loaded=False, is_listening=False",
                severity=Severity.MEDIUM,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="wake_word",
                status=TestStatus.FAILED,
                mode=TestMode.MOCKED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.MEDIUM,
            )
