"""
Command-Line Interface (CLI) for the Resource-Constrained Local AI Assistant.
Provides interactive chat, telemetry display, diagnostic commands, and low-resource mode.
"""

import argparse
import sys
from pathlib import Path

from src.adapter.llama_server import LlamaServerManager
from src.adapter.llm_client import LocalLlmClient
from src.agent.audit_log import AuditLogger
from src.agent.orchestrator import SafeAgentOrchestrator
from src.agent.policy_engine import PolicyEngine
from src.core.config import get_default_settings
from src.core.governor import ResourceGovernor


def print_banner(settings, telemetry):
    print("=================================================================")
    print("      Resource-Constrained Desktop AI Assistant (Offline)        ")
    print("=================================================================")
    print(f"  Model:           {settings.model_path.name}")
    print(f"  Inference Host:  http://{settings.network.server_host}:{settings.network.server_port}")
    print(f"  GPU Offload:     {settings.governor.gpu_layers} layers")
    print(f"  CPU Threads:     {settings.governor.cpu_threads}")
    print(f"  Context Window:  {settings.governor.max_context_tokens} tokens")
    print(f"  Process Priority:{settings.governor.process_priority}")
    print(f"  RAM Usage:       {telemetry.ram_used_gb:.1f} / {telemetry.ram_total_gb:.1f} GB ({telemetry.ram_percent}%)")
    if telemetry.gpu_vram_used_mb is not None:
        print(f"  GPU VRAM Usage:  {telemetry.gpu_vram_used_mb:.0f} / {telemetry.gpu_vram_total_mb:.0f} MB")
    print("=================================================================")
    print("Commands: /exit (quit), /status (hardware telemetry), /reset (clear chat)")
    print("=================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Run the offline local desktop AI assistant.")
    parser.add_argument("--low-resource", action="store_true", help="Run with low-resource profile (fewer threads & layers)")
    parser.add_argument("--cpu-only", action="store_true", help="Force CPU-only execution (0 GPU offload layers)")
    args = parser.parse_args()

    settings = get_default_settings(low_resource=args.low_resource)
    if args.cpu_only:
        settings.governor.gpu_layers = 0

    # Initialize components
    governor = ResourceGovernor(settings.governor)
    server_mgr = LlamaServerManager(settings, governor=governor)

    # Set idle unload callback
    governor.on_idle_timeout = server_mgr.stop

    client = LocalLlmClient(settings)
    policy_engine = PolicyEngine()
    audit_logger = AuditLogger(settings.log_dir)
    orchestrator = SafeAgentOrchestrator(client, policy_engine, audit_logger, governor=governor)

    print("[*] Launching local inference server...")
    try:
        server_mgr.start(timeout_seconds=45)
    except Exception as e:
        print(f"[ERROR] Failed to start llama-server: {e}", file=sys.stderr)
        sys.exit(1)

    governor.start_idle_monitor()
    telemetry = governor.get_system_telemetry()
    print_banner(settings, telemetry)

    try:
        while True:
            try:
                user_input = input("User > ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input:
                continue

            if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                break

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
                # Ensure server is running (load-on-demand)
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
        governor.stop_idle_monitor()
        server_mgr.stop()
        print("[+] Assistant stopped cleanly.")


if __name__ == "__main__":
    main()
