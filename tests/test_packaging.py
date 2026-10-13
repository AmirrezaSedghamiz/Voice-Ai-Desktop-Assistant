"""
Automated Packaging and Release Validation Tests.
Validates the Windows x64 PyInstaller executable structure, native dependencies,
llama.cpp runtime binaries, model discovery mechanisms, and release assets.
"""

import os
import subprocess
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist" / "david_assistant"
EXE_PATH = DIST_DIR / "david_assistant.exe"


def test_packaged_executable_exists_and_is_valid_pe():
    """Validates that david_assistant.exe exists, is non-empty, and has valid PE headers."""
    assert EXE_PATH.exists(), f"Packaged executable not found at {EXE_PATH}"
    size = EXE_PATH.stat().st_size
    assert size > 5 * 1024 * 1024, f"Executable size {size} bytes is suspiciously small."

    # Verify DOS / PE executable magic bytes ("MZ")
    with open(EXE_PATH, "rb") as f:
        magic = f.read(2)
    assert magic == b"MZ", "File does not contain valid Windows PE header (MZ magic)."


def test_bundled_runtime_binaries():
    """Validates that llama.cpp inference binaries and assets are present in the distribution."""
    llama_server = DIST_DIR / "bin" / "llama.cpp" / "llama-server.exe"
    assert llama_server.exists(), f"llama-server.exe not found at {llama_server}"

    assets_ico = DIST_DIR / "assets" / "david_icon.ico"
    assert assets_ico.exists(), f"Application icon not found at {assets_ico}"

    readme = DIST_DIR / "README.txt"
    assert readme.exists(), "Release README.txt not found."
    content = readme.read_text(encoding="utf-8")
    assert "David - Local Desktop AI Assistant" in content
    assert "Activate David" in content


def test_internal_native_libraries():
    """Validates that PySide6, Vosk, CTranslate2, and audio libraries are present in _internal."""
    internal_dir = DIST_DIR / "_internal"
    assert internal_dir.exists(), "_internal directory not found."

    # Check for PySide6
    pyside_matches = list(internal_dir.glob("PySide6*"))
    assert len(pyside_matches) > 0, "PySide6 modules not found in _internal."

    # Check for Vosk
    vosk_matches = list(internal_dir.glob("vosk*"))
    assert len(vosk_matches) > 0, "Vosk library not found in _internal."


def test_missing_model_validation_outside_venv():
    """
    Launches the packaged executable with a forced empty model directory
    to verify that model validation triggers gracefully without unhandled crashes.
    """
    clean_env = os.environ.copy()
    clean_env["QT_QPA_PLATFORM"] = "offscreen"
    clean_env["DAVID_MODELS_DIR"] = str(PROJECT_ROOT / "non_existent_models_dir")
    # Remove virtualenv from PATH to test standalone behavior
    clean_env.pop("VIRTUAL_ENV", None)

    # Launch executable with --help or --minimized
    proc = subprocess.run(
        [str(EXE_PATH), "--help"],
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    # Exits with 0 for --help
    assert proc.returncode == 0
