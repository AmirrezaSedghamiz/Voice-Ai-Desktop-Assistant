"""
Release Packaging Script for David Desktop Assistant.
Assembles the complete Windows x64 distribution bundle in dist/david_assistant:
- Runs PyInstaller build
- Copies llama.cpp server binaries into dist/david_assistant/bin/llama.cpp
- Bundles application assets and icons
- Writes release documentation and model provisioning guide
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist" / "david_assistant"


def build_pyinstaller() -> None:
    """Builds the main executable using PyInstaller spec."""
    print("[*] Running PyInstaller release build...")
    spec_path = PROJECT_ROOT / "david_assistant.spec"
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_path)],
        cwd=str(PROJECT_ROOT),
        check=True,
    )
    print("[+] PyInstaller build complete.")


def bundle_binaries_and_assets() -> None:
    """Copies llama.cpp server binaries and icons into the distribution folder."""
    print("[*] Bundling runtime binaries and assets...")

    # 1. llama.cpp server binaries
    src_bin = PROJECT_ROOT / "bin" / "llama.cpp"
    dst_bin = DIST_DIR / "bin" / "llama.cpp"
    if src_bin.exists():
        dst_bin.parent.mkdir(parents=True, exist_ok=True)
        if dst_bin.exists():
            shutil.rmtree(dst_bin)
        shutil.copytree(src_bin, dst_bin)
        print(f"[+] Bundled llama.cpp runtime binaries into {dst_bin}")

    # 2. Assets (icons)
    src_assets = PROJECT_ROOT / "assets"
    dst_assets = DIST_DIR / "assets"
    if src_assets.exists():
        dst_assets.parent.mkdir(parents=True, exist_ok=True)
        if dst_assets.exists():
            shutil.rmtree(dst_assets)
        shutil.copytree(src_assets, dst_assets)
        print(f"[+] Bundled assets into {dst_assets}")

    # 3. Create models directory with provisioning guide
    dst_models = DIST_DIR / "models"
    dst_models.mkdir(parents=True, exist_ok=True)

    models_readme = dst_models / "README_MODELS.txt"
    models_readme.write_text(
        "=================================================================\n"
        "David Desktop Assistant - Local AI Models Directory\n"
        "=================================================================\n"
        "This folder contains the local, offline neural models for David:\n\n"
        "1. LLM Reasoning Model:\n"
        "   - Path: models/Qwen3-1.7B-Q4_K_M.gguf\n"
        "   - Architecture: Qwen 2.5/3 (GGUF 4-bit quantized)\n"
        "   - License: Apache 2.0\n\n"
        "2. Speech-to-Text (STT) Model:\n"
        "   - Path: models/stt/whisper-base/\n"
        "   - Architecture: faster-whisper (CTranslate2 INT8 quantized)\n"
        "   - License: MIT\n\n"
        "3. Text-to-Speech (TTS) Voice Model:\n"
        "   - Path: models/tts/en_US-lessac-medium.onnx (+ .json)\n"
        "   - Architecture: Piper ONNX neural voice\n"
        "   - License: MIT\n\n"
        "4. Wake-Word Acoustic Model:\n"
        "   - Path: models/wake_word/vosk-model-small-en-us-0.15/\n"
        "   - Architecture: Vosk Kaldi keyword spotter ('Activate David')\n"
        "   - License: Apache 2.0\n\n"
        "If copying from the development environment, simply copy the entire\n"
        "'models' folder from the source repository into this directory.\n"
        "=================================================================\n",
        encoding="utf-8",
    )
    print(f"[+] Created models directory template at {dst_models}")

    # 4. Release README
    release_readme = DIST_DIR / "README.txt"
    release_readme.write_text(
        "=================================================================\n"
        "                  David - Local Desktop AI Assistant            \n"
        "             Offline Voice, Task Automation & Memory            \n"
        "=================================================================\n\n"
        "OVERVIEW:\n"
        "David is a fully local, offline Windows AI voice assistant designed\n"
        "for privacy, low resource consumption, and desktop task automation.\n\n"
        "HOW TO RUN:\n"
        "1. Double-click 'david_assistant.exe' to launch the assistant.\n"
        "2. No Python installation or virtual environment activation is required.\n\n"
        "VOICE ACTIVATION:\n"
        "- Activation phrase: Say 'Activate David' to begin hands-free voice interaction.\n"
        "- Manual Voice: Click the 'Speak' button in the application window.\n"
        "- Text Mode: Type any request in English or Persian and press Enter.\n\n"
        "PRIVACY & OFFLINE SECURITY:\n"
        "- 100% Local: All models run locally on your CPU/GPU.\n"
        "- Zero Cloud: No audio, text, or telemetry is ever transmitted over the network.\n"
        "- Local Storage: Persistent memory and settings are kept in the 'data' directory.\n\n"
        "HARDWARE REQUIREMENTS:\n"
        "- OS: Windows 10 or Windows 11 (64-bit)\n"
        "- RAM: 8 GB minimum (16-24 GB recommended)\n"
        "- GPU: NVIDIA RTX 3050 Ti or higher recommended (CUDA accelerated)\n"
        "- CPU: 4+ cores for smooth STT and TTS synthesis\n\n"
        "SETTINGS & CUSTOMIZATION:\n"
        "Open Settings (gear icon in the header) to configure:\n"
        "- Wake-word detection toggle and microphone sensitivity\n"
        "- Audio input and output devices\n"
        "- System tray minimization behavior\n"
        "- Spoken voice responses (TTS)\n"
        "=================================================================\n",
        encoding="utf-8",
    )
    print(f"[+] Created release documentation at {release_readme}")


def main() -> None:
    print("=== Assembling David Assistant Windows x64 Release ===")
    build_pyinstaller()
    bundle_binaries_and_assets()
    print("\n[SUCCESS] Release package assembled successfully at:")
    print(f"  {DIST_DIR}")


if __name__ == "__main__":
    main()
