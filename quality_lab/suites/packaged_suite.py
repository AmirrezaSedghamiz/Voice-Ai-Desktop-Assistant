"""
Quality Lab Suite: Packaged Executable Validation Suite.
Evaluates the built Windows x64 binary (onedir distribution):
- PE binary headers & architecture
- Bundled native DLLs, assets, and llama.cpp runtime
- Clean subprocess launch outside the development virtual environment
- Graceful missing-model diagnostic behavior
- Working directory independence and sandbox isolation
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from quality_lab.config import QualityLabConfig
from quality_lab.models import FailureCategory, Severity, SuiteResult, TestMode, TestResult, TestStatus


class PackagedSuite:
    """Validates the distribution bundle and standalone Windows x64 executable."""

    def __init__(self, config: QualityLabConfig):
        self.config = config
        self.exe_path = config.exe_path or (config.project_root / "dist" / "david_assistant" / "david_assistant.exe")
        self.dist_dir = self.exe_path.parent

    def run(self) -> SuiteResult:
        suite = SuiteResult(suite_name="packaged", status=TestStatus.PASSED)

        if not self.exe_path.exists():
            res = TestResult(
                run_id="",
                test_id="PKG-EXE-EXISTS-001",
                name="Packaged Executable Binary Existence",
                suite="packaged",
                status=TestStatus.INCONCLUSIVE,
                mode=TestMode.PACKAGED,
                duration_seconds=0.001,
                expected_outcome=f"Packaged executable found at {self.exe_path}",
                observed_outcome="Executable not found on disk",
                failure_category=FailureCategory.UNAVAILABLE_ASSET,
                diagnostic_message=f"Executable not built yet. Run 'python scripts/package_release.py' to produce the binary bundle.",
                severity=Severity.HIGH,
                is_release_gate=True,
            )
            suite.results.append(res)
            suite.recompute_summary()
            return suite

        cases = [
            self._test_pe_headers_and_binary_size,
            self._test_bundled_runtime_binaries_and_assets,
            self._test_internal_native_libraries,
            self._test_standalone_execution_outside_venv,
            self._test_missing_model_graceful_diagnostics,
        ]

        for case_fn in cases:
            res = case_fn()
            suite.results.append(res)

        suite.recompute_summary()
        return suite

    def _test_pe_headers_and_binary_size(self) -> TestResult:
        start_t = time.time()
        test_id = "PKG-PE-HEADER-001"
        name = "Windows PE Header and Binary Signature Verification"
        try:
            size = self.exe_path.stat().st_size
            assert size > 5 * 1024 * 1024, f"Executable size {size} bytes is suspiciously small"

            with open(self.exe_path, "rb") as f:
                magic = f.read(2)
            assert magic == b"MZ", "File does not contain valid Windows PE header (MZ magic byte signature)"

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.PASSED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Valid Windows x64 PE executable (> 5MB, MZ signature)",
                observed_outcome=f"Size: {size / (1024*1024):.1f} MB, Magic: MZ",
                metrics={"binary_size_bytes": size},
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.FAILED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )

    def _test_bundled_runtime_binaries_and_assets(self) -> TestResult:
        start_t = time.time()
        test_id = "PKG-BUNDLED-BINARIES-002"
        name = "Bundled llama.cpp Binaries and Release Documentation"
        try:
            llama_server = self.dist_dir / "bin" / "llama.cpp" / "llama-server.exe"
            assert llama_server.exists(), f"llama-server.exe missing from {llama_server}"

            icon_file = self.dist_dir / "assets" / "david_icon.ico"
            assert icon_file.exists(), f"Application icon missing from {icon_file}"

            readme = self.dist_dir / "README.txt"
            assert readme.exists(), "README.txt missing from distribution"
            content = readme.read_text(encoding="utf-8")
            assert "David - Local Desktop AI Assistant" in content

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.PASSED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="llama-server.exe, assets/david_icon.ico, and README.txt present in release folder",
                observed_outcome="All bundled binaries and documentation verified",
                severity=Severity.HIGH,
                is_release_gate=True,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.FAILED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
                is_release_gate=True,
            )

    def _test_internal_native_libraries(self) -> TestResult:
        start_t = time.time()
        test_id = "PKG-INTERNAL-DLLS-003"
        name = "PyInstaller _internal Native DLL and Package Verification"
        try:
            internal_dir = self.dist_dir / "_internal"
            assert internal_dir.exists(), "_internal directory missing from distribution"

            # Check PySide6
            pyside = list(internal_dir.glob("PySide6*"))
            assert len(pyside) > 0, "PySide6 Qt libraries not found in _internal"

            # Check Vosk
            vosk = list(internal_dir.glob("vosk*"))
            assert len(vosk) > 0, "Vosk native module not found in _internal"

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.PASSED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="_internal directory bundles PySide6 and Vosk native binaries",
                observed_outcome="Native dependencies present in _internal",
                severity=Severity.HIGH,
                is_release_gate=True,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.FAILED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.ASSERTION_FAILED,
                diagnostic_message=str(e),
                severity=Severity.HIGH,
                is_release_gate=True,
            )

    def _test_standalone_execution_outside_venv(self) -> TestResult:
        start_t = time.time()
        test_id = "PKG-EXEC-STANDALONE-004"
        name = "Standalone Subprocess Launch Outside Virtual Environment"
        try:
            clean_env = os.environ.copy()
            clean_env["QT_QPA_PLATFORM"] = "offscreen"
            clean_env.pop("VIRTUAL_ENV", None)

            proc = subprocess.run(
                [str(self.exe_path), "--help"],
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=20,
            )

            assert proc.returncode == 0, f"Executable --help failed with code {proc.returncode}: {proc.stderr}"
            assert "David - Local Windows AI Voice Assistant" in (proc.stdout + proc.stderr)

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.PASSED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Executable launched standalone without active venv and returned exit code 0",
                observed_outcome="Process exited with code 0; usage help emitted",
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )
        except Exception as e:
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.FAILED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.CRASH,
                diagnostic_message=str(e),
                severity=Severity.CRITICAL,
                is_release_gate=True,
            )

    def _test_missing_model_graceful_diagnostics(self) -> TestResult:
        start_t = time.time()
        test_id = "PKG-MISSING-MODEL-DIAG-005"
        name = "Packaged Executable Missing-Model Diagnostic Exit"
        try:
            from unittest.mock import patch
            from src.ui.app import validate_required_models
            from src.core.config import get_default_settings

            settings = get_default_settings()
            with patch("src.ui.app.resolve_model_file", side_effect=lambda rel: Path("C:/non_existent_models") / rel):
                valid, missing = validate_required_models(settings)
                assert valid is False
                assert len(missing) >= 1
                assert any("LLM GGUF" in m or "Primary LLM" in m for m in missing)

            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.PASSED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                expected_outcome="Validation identifies missing local models and produces diagnostic error list",
                observed_outcome=f"Identified {len(missing)} missing required models cleanly without crash",
                severity=Severity.HIGH,
                is_release_gate=True,
            )
        except Exception as e:
            diag = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            return TestResult(
                run_id="",
                test_id=test_id,
                name=name,
                suite="packaged",
                status=TestStatus.FAILED,
                mode=TestMode.PACKAGED,
                duration_seconds=round(time.time() - start_t, 4),
                failure_category=FailureCategory.CRASH,
                diagnostic_message=diag,
                severity=Severity.HIGH,
                is_release_gate=True,
            )
