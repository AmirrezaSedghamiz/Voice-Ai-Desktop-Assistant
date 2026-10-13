"""
Command-Line Interface (CLI) for the Resource-Constrained Local AI Assistant.
Provides interactive chat, telemetry display, diagnostic commands, and full voice interaction.
"""

import argparse
import sys
import threading
from pathlib import Path

from src.adapter.llama_server import LlamaServerManager
from src.adapter.llm_client import LocalLlmClient
from src.agent.audit_log import AuditLogger
from src.agent.orchestrator import SafeAgentOrchestrator
from src.agent.policy_engine import PolicyEngine
from src.core.config import get_default_settings
from src.core.governor import ResourceGovernor


def print_banner(settings, telemetry, voice_enabled=False, trigger_mode="ptt"):
    print("=================================================================")
    print("      Resource-Constrained Desktop AI Assistant (Offline)        ")
    print("=================================================================")
    print(f"  Model:           {settings.model_path.name}")
    print(f"  Inference Host:  http://{settings.network.server_host}:{settings.network.server_port}")
    print(f"  GPU Offload:     {settings.governor.gpu_layers} layers")
    print(f"  CPU Threads:     {settings.governor.cpu_threads}")
    print(f"  Context Window:  {settings.governor.max_context_tokens} tokens")
    print(f"  Process Priority:{settings.governor.process_priority}")
    print(f"  Mode:            {'VOICE (' + trigger_mode.upper() + ')' if voice_enabled else 'TEXT CHAT'}")
    print(f"  RAM Usage:       {telemetry.ram_used_gb:.1f} / {telemetry.ram_total_gb:.1f} GB ({telemetry.ram_percent}%)")
    if telemetry.gpu_vram_used_mb is not None:
        print(f"  GPU VRAM Usage:  {telemetry.gpu_vram_used_mb:.0f} / {telemetry.gpu_vram_total_mb:.0f} MB")
    print("=================================================================")
    print("Commands: /exit (quit), /status (hardware telemetry), /reset (clear chat)")
    if voice_enabled:
        print("Voice:    Press [Enter] to speak, or type 't' to switch to text mode")
    else:
        print("Voice:    Type '/voice' to activate voice mode")
    print("=================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Run the offline local desktop AI assistant.")
    parser.add_argument("--low-resource", action="store_true", help="Run with low-resource profile (fewer threads & layers)")
    parser.add_argument("--cpu-only", action="store_true", help="Force CPU-only execution (0 GPU offload layers)")
    parser.add_argument("--voice", action="store_true", help="Start in voice interaction mode (STT -> LLM -> TTS)")
    parser.add_argument("--trigger-mode", choices=["ptt", "vad"], default="ptt", help="Voice trigger mode: 'ptt' or 'vad'")
    parser.add_argument("--no-tts", action="store_true", help="Disable spoken response (text display only)")
    parser.add_argument("--voice-speed", type=float, default=1.0, help="Speech rate multiplier (default: 1.0)")
    args = parser.parse_args()

    settings = get_default_settings(low_resource=args.low_resource)
    if args.cpu_only:
        settings.governor.gpu_layers = 0

    from src.memory.store import MemoryStore

    # Initialize core reasoning, memory, & policy components
    governor = ResourceGovernor(settings.governor)
    server_mgr = LlamaServerManager(settings, governor=governor)
    governor.on_idle_timeout = server_mgr.stop

    client = LocalLlmClient(settings)
    policy_engine = PolicyEngine()
    audit_logger = AuditLogger(settings.log_dir)
    memory_store = MemoryStore(settings.memory)
    orchestrator = SafeAgentOrchestrator(
        client,
        policy_engine,
        audit_logger,
        governor=governor,
        memory_store=memory_store,
    )

    # Voice subsystem setup (if requested)
    voice_session = None
    voice_active = args.voice

    if voice_active:
        try:
            from src.audio.config import AudioConfig
            from src.audio.voice_session import VoiceSessionManager

            audio_cfg = AudioConfig(
                trigger_mode=args.trigger_mode,
                tts_enabled=not args.no_tts,
                tts_speed=args.voice_speed,
            )

            # Validate voice assets
            if not audio_cfg.tts_model_path.exists() or not (audio_cfg.stt_model_dir / "model.bin").exists():
                print(
                    "[ERROR] Required voice models not found.\n"
                    "Please run 'python scripts/download_assets.py --voice' to provision STT and TTS models.",
                    file=sys.stderr,
                )
                sys.exit(1)

            voice_session = VoiceSessionManager(orchestrator, audio_cfg)
            print("[*] Pre-loading local voice models (CPU mode)...")
            voice_session.initialize_models()
        except ImportError as e:
            print(f"[ERROR] Audio dependencies not installed: {e}", file=sys.stderr)
            print("Run 'pip install -r requirements.txt' to install sounddevice, faster-whisper, and piper-tts.")
            sys.exit(1)

    print("[*] Launching local inference server...")
    try:
        server_mgr.start(timeout_seconds=45)
    except Exception as e:
        print(f"[ERROR] Failed to start llama-server: {e}", file=sys.stderr)
        sys.exit(1)

    governor.start_idle_monitor()
    telemetry = governor.get_system_telemetry()
    print_banner(settings, telemetry, voice_enabled=voice_active, trigger_mode=args.trigger_mode)

    try:
        while True:
            # -------------------------------------------------------------
            # VOICE MODE (Push-to-Talk or VAD)
            # -------------------------------------------------------------
            if voice_active and voice_session is not None:
                if args.trigger_mode == "ptt":
                    try:
                        prompt_str = "Voice [Press Enter to speak | 't' for text | '/exit' to quit] > "
                        user_cmd = input(prompt_str).strip()
                    except (KeyboardInterrupt, EOFError):
                        break

                    if user_cmd.lower() in ("/exit", "/quit", "exit", "quit"):
                        break
                    if user_cmd.lower() in ("t", "/text", "text"):
                        voice_active = False
                        print("[*] Switched to text interaction mode.\n")
                        continue
                    if user_cmd.lower() == "/status":
                        t = governor.get_system_telemetry()
                        print(f"[Telemetry] CPU: {t.cpu_percent}% | RAM: {t.ram_used_gb}/{t.ram_total_gb} GB ({t.ram_percent}%) | VRAM: {t.gpu_vram_used_mb or 'N/A'}/{t.gpu_vram_total_mb or 'N/A'} MB\n")
                        continue
                    if user_cmd.lower() == "/reset":
                        orchestrator.reset_conversation()
                        print("[*] Conversation context reset.\n")
                        continue

                    # Execute PTT recording
                    stop_event = threading.Event()
                    recorded_audio = []

                    def do_ptt_record():
                        audio = voice_session.recorder.record_ptt(stop_event)
                        recorded_audio.append(audio)

                    rec_thread = threading.Thread(target=do_ptt_record, daemon=True)
                    rec_thread.start()

                    print("[*] [MIC RECORDING...] Speak now (take your time). Press [Enter] when done > ", end="", flush=True)
                    try:
                        input()
                    except (KeyboardInterrupt, EOFError):
                        stop_event.set()
                        rec_thread.join()
                        break
                    stop_event.set()
                    rec_thread.join()

                    if not recorded_audio or len(recorded_audio[0]) == 0:
                        print("\n[!] No audio captured. Try again.\n")
                        continue

                    audio_data = recorded_audio[0]

                else:
                    # Continuous VAD Mode
                    print("\n[*] [VAD LISTENING...] Speak into microphone (Ctrl+C to pause) > ", flush=True)
                    cancel_event = threading.Event()
                    try:
                        audio_data = voice_session.recorder.record_vad(cancel_event=cancel_event)
                    except KeyboardInterrupt:
                        print("\n[*] VAD paused. Type 'c' to continue or 't' for text mode: ", end="", flush=True)
                        choice = input().strip().lower()
                        if choice in ("t", "text"):
                            voice_active = False
                        continue

                    if audio_data is None or len(audio_data) == 0:
                        continue

                # Process turn through VoiceSessionManager
                print("[*] Transcribing speech...", end="", flush=True)
                # Ensure server is running (load-on-demand)
                if not server_mgr.is_running:
                    print("\n[*] Model was idle/unloaded. Reloading server...", end="", flush=True)
                    server_mgr.start()

                def on_transcript(text, lang):
                    print(f"\rUser (Voice) > {text}  [Lang: {lang}]\nAssistant > ", end="", flush=True)

                def on_response(text):
                    print(f"{text}")

                turn_result = voice_session.process_voice_turn(
                    audio_data=audio_data,
                    on_transcribed_callback=on_transcript,
                    on_assistant_response_callback=on_response,
                )

                if turn_result.llm_metrics:
                    m = turn_result.llm_metrics
                    spoken_tag = "Spoken via TTS" if turn_result.spoken else "Text only"
                    print(f"  [{m.completion_tokens} tokens | {m.tokens_per_second:.1f} t/s | STT: {turn_result.stt_latency_s:.2f}s | TTS: {turn_result.tts_latency_s:.2f}s | {spoken_tag}]\n")

            # -------------------------------------------------------------
            # TEXT MODE
            # -------------------------------------------------------------
            else:
                try:
                    user_input = input("User > ").strip()
                except (KeyboardInterrupt, EOFError):
                    break

                if not user_input:
                    continue

                if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                    break

                if user_input.lower() in ("/voice", "voice"):
                    if voice_session is None:
                        try:
                            from src.audio.config import AudioConfig
                            from src.audio.voice_session import VoiceSessionManager
                            audio_cfg = AudioConfig(
                                trigger_mode=args.trigger_mode,
                                tts_enabled=not args.no_tts,
                                tts_speed=args.voice_speed,
                            )
                            voice_session = VoiceSessionManager(orchestrator, audio_cfg)
                            voice_session.initialize_models()
                        except Exception as e:
                            print(f"[ERROR] Could not initialize voice mode: {e}\n")
                            continue
                    voice_active = True
                    print("[*] Switched to voice interaction mode.\n")
                    continue

                if user_input.lower() == "/reset":
                    orchestrator.reset_conversation()
                    print("[*] Conversation context reset.\n")
                    continue

                if user_input.lower() == "/status":
                    t = governor.get_system_telemetry()
                    print(f"[Telemetry] CPU: {t.cpu_percent}% | RAM: {t.ram_used_gb}/{t.ram_total_gb} GB ({t.ram_percent}%) | VRAM: {t.gpu_vram_used_mb or 'N/A'}/{t.gpu_vram_total_mb or 'N/A'} MB\n")
                    continue

                print("Assistant > ", end="", flush=True)
                try:
                    if not server_mgr.is_running:
                        print("\n[*] Model was idle/unloaded. Reloading...", end="", flush=True)
                        server_mgr.start()
                        print(" Ready.\nAssistant > ", end="", flush=True)

                    response_text, metrics = orchestrator.handle_user_input(user_input)
                    print(f"{response_text}")
                    print(f"  [{metrics.completion_tokens} tokens | {metrics.tokens_per_second:.1f} t/s | {metrics.total_generation_time:.2f}s]\n")
                except Exception as e:
                    print(f"\n[ERROR] Inference failed: {e}\n", file=sys.stderr)

    finally:
        print("\n[*] Shutting down...")
        if voice_session:
            voice_session.unload()
        memory_store.close()
        governor.stop_idle_monitor()
        server_mgr.stop()
        print("[+] Assistant stopped cleanly.")


if __name__ == "__main__":
    main()
