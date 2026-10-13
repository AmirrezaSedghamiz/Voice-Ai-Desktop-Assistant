"""
Application Bootstrap and Lifecycle Management:
Initializes the Qt application, verifies offline model provisioning,
launches background services, and displays the main David assistant window.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from src.adapter.llama_server import LlamaServerManager
from src.adapter.llm_client import LocalLlmClient
from src.agent.audit_log import AuditLogger
from src.agent.orchestrator import SafeAgentOrchestrator
from src.agent.policy_engine import PolicyEngine
from src.agent.tools.handlers.tasks import TaskManager
from src.audio.config import AudioConfig
from src.audio.voice_session import VoiceSessionManager
from src.core.config import get_default_settings
from src.core.governor import ResourceGovernor
from src.memory.store import MemoryStore
from src.ui.config import UiConfig
from src.ui.icon import ensure_icon_files, get_app_icon
from src.ui.main_window import MainWindow

logger = logging.getLogger("assistant.ui.app")
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def setup_application_logging() -> None:
    """Configures rotating console and file logging in the writable data/logs directory."""
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "david_desktop.log"

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


def resolve_model_file(rel_path: str) -> Path:
    """Finds a model file checking local app dir, custom env dir, and dev workspace fallback."""
    candidates = [
        PROJECT_ROOT / "models" / rel_path,
        PROJECT_ROOT.parent.parent / "models" / rel_path,
    ]
    if "DAVID_MODELS_DIR" in os.environ:
        candidates.insert(0, Path(os.environ["DAVID_MODELS_DIR"]) / rel_path)
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def validate_required_models(settings) -> tuple[bool, list[str]]:
    """Checks whether the necessary local models exist before starting."""
    missing = []

    # 1. LLM GGUF
    llm_path = resolve_model_file("Qwen3-1.7B-Q4_K_M.gguf")
    if not llm_path.exists():
        missing.append(f"Primary LLM GGUF model: {llm_path}")
    else:
        settings.model_path = llm_path

    # 2. STT Whisper
    stt_model_dir = resolve_model_file("stt/whisper-base")
    if not (stt_model_dir / "model.bin").exists():
        missing.append(f"STT Whisper model: {stt_model_dir / 'model.bin'}")

    # 3. TTS Piper
    tts_model_path = resolve_model_file("tts/en_US-lessac-medium.onnx")
    if not tts_model_path.exists():
        missing.append(f"TTS Piper model: {tts_model_path}")

    # 4. Wake-Word Vosk
    ww_model_dir = resolve_model_file("wake_word/vosk-model-small-en-us-0.15")
    if not ww_model_dir.exists():
        missing.append(f"Wake-Word Vosk model directory: {ww_model_dir}")

    return (len(missing) == 0, missing)


def main() -> None:
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="David - Local Windows AI Voice Assistant")
    parser.add_argument("--low-resource", action="store_true", help="Run with reduced thread/layer profile")
    parser.add_argument("--cpu-only", action="store_true", help="Force CPU-only LLM inference")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to the system tray")
    args = parser.parse_args()

    setup_application_logging()
    logger.info("Initializing David Local Desktop Assistant...")

    # Load UI configurations and assets
    ui_config = UiConfig.load()
    if args.minimized:
        ui_config.start_minimized = True

    # Initialize Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("David")
    app.setApplicationDisplayName("David - Local AI Assistant")
    app.setOrganizationName("OfflineDavid")

    ensure_icon_files()
    app_icon = get_app_icon()
    app.setWindowIcon(app_icon)

    # Core settings and model validation
    settings = get_default_settings(low_resource=args.low_resource)
    if args.cpu_only:
        settings.governor.gpu_layers = 0

    valid, missing_models = validate_required_models(settings)
    if not valid:
        err_msg = (
            "The following required local models could not be found:\n\n"
            + "\n".join(f" - {m}" for m in missing_models)
            + "\n\nPlease ensure your models directory is provisioned before running David."
        )
        logger.error(err_msg)
        QMessageBox.critical(None, "Missing Local Models", err_msg)
        sys.exit(1)

    # Resource Governor & Llama Server Manager
    governor = ResourceGovernor(settings.governor)
    server_mgr = LlamaServerManager(settings, governor=governor)
    governor.on_idle_timeout = server_mgr.stop

    # Ensure local llama-server is active
    server_mgr.ensure_server_running()

    # Core LLM Client, Memory, Task Manager, & Safe Agent Orchestrator
    llm_client = LocalLlmClient(settings)
    policy_engine = PolicyEngine()
    audit_logger = AuditLogger(settings.log_dir)
    memory_store = MemoryStore(settings.memory)
    task_manager = TaskManager(settings.data_dir / "tasks.db")

    orchestrator = SafeAgentOrchestrator(
        llm_client=llm_client,
        policy_engine=policy_engine,
        audit_logger=audit_logger,
        governor=governor,
        memory_store=memory_store,
        task_manager=task_manager,
    )

    # Voice Session Subsystem
    audio_cfg = AudioConfig(
        trigger_mode=ui_config.trigger_mode,
        tts_enabled=ui_config.tts_enabled,
        input_device_index=ui_config.input_device_index,
        output_device_index=ui_config.output_device_index,
        stt_language="fa",  # Persian bias by default
        stt_model_dir=resolve_model_file("stt/whisper-base"),
        tts_model_path=resolve_model_file("tts/en_US-lessac-medium.onnx"),
        tts_config_path=resolve_model_file("tts/en_US-lessac-medium.onnx.json"),
    )
    voice_session = VoiceSessionManager(orchestrator, audio_cfg)

    try:
        voice_session.initialize_models()
    except Exception as e:
        logger.warning("Could not pre-load voice models: %s", e)

    # Create Main Window
    window = MainWindow(
        orchestrator=orchestrator,
        voice_session=voice_session,
        ui_config=ui_config,
    )

    if not ui_config.start_minimized:
        window.show()
    else:
        logger.info("Application started minimized to system tray.")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
