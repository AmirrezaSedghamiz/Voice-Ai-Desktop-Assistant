"""
Standardized Benchmark & Evaluation Suite.
Measures Time-To-First-Token (TTFT), throughput (tokens/sec), CPU load, RAM usage,
and VRAM footprint across English and Persian evaluation prompts.
"""

import json
import logging
import sys
import time
from pathlib import Path

# Enforce UTF-8 encoding for Windows console (required for Persian text)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.adapter.llama_server import LlamaServerManager
from src.adapter.llm_client import LocalLlmClient
from src.core.config import get_default_settings
from src.core.governor import ResourceGovernor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("assistant.benchmark")

BENCHMARK_PROMPTS = [
    {
        "id": "en_short",
        "language": "English",
        "description": "Short factual prompt",
        "prompt": "What is the capital of France and what is its primary landmark? Answer concisely in two sentences.",
    },
    {
        "id": "en_reasoning",
        "language": "English",
        "description": "Logical reasoning and formatting",
        "prompt": "A customer bought 3 apples for $2 each and 2 oranges for $3 each. How much did they spend in total? Show step-by-step calculation.",
    },
    {
        "id": "fa_factual",
        "language": "Persian",
        "description": "Factual Persian comprehension & syntax",
        "prompt": "پایتخت کشور ایران کدام شهر است و چه تعداد جمعیت تقریبی دارد؟ در یک جمله کوتاه پاسخ دهید.",
    },
    {
        "id": "fa_grammar",
        "language": "Persian",
        "description": "Complex Persian phrasing and vocabulary",
        "prompt": "تفاوت بین هوش مصنوعی نمادین و یادگیری عمیق را در دو بند کوتاه به زبان فارسی توضیح دهید.",
    },
]


def run_benchmark(low_resource: bool = False, output_file: Path | None = None) -> list[dict]:
    settings = get_default_settings(low_resource=low_resource)
    governor = ResourceGovernor(settings.governor)
    server_mgr = LlamaServerManager(settings, governor=governor)
    client = LocalLlmClient(settings)

    print(f"\n[*] Starting inference server for benchmarking (Model: {settings.model_path.name})...")
    server_mgr.start(timeout_seconds=45)

    results = []

    try:
        # Warmup turn
        print("[*] Running warmup query...")
        client.chat_completion([{"role": "user", "content": "Hello"}])

        print("\n=========================================================================================")
        print(f"               BENCHMARK EXECUTION (GPU Layers: {settings.governor.gpu_layers}, Threads: {settings.governor.cpu_threads})")
        print("=========================================================================================")

        for item in BENCHMARK_PROMPTS:
            print(f"\n--> Test [{item['id']}] ({item['language']} - {item['description']})")
            print(f"    Prompt: {item['prompt']}")

            # Telemetry before turn
            t_before = governor.get_system_telemetry()

            # Execute inference turn
            messages = [{"role": "user", "content": item["prompt"]}]
            t_before = governor.get_system_telemetry()
            
            response_text, metrics = client.chat_completion(messages)
            
            t_after = governor.get_system_telemetry()

            result_entry = {
                "id": item["id"],
                "language": item["language"],
                "description": item["description"],
                "prompt_tokens": metrics.prompt_tokens,
                "tokens_generated": metrics.completion_tokens,
                "tokens_per_second": round(metrics.tokens_per_second, 2),
                "total_time_seconds": round(metrics.total_generation_time, 3),
                "ram_used_gb": t_after.ram_used_gb,
                "vram_used_mb": t_after.gpu_vram_used_mb,
                "response_preview": response_text[:140].replace("\n", " ") + ("..." if len(response_text) > 140 else ""),
            }
            results.append(result_entry)

            print(f"    Output: {result_entry['response_preview']}")
            print(f"    TPS: {result_entry['tokens_per_second']} t/s | Total Time: {result_entry['total_time_seconds']}s | Generated Tokens: {result_entry['tokens_generated']}")
            print(f"    VRAM: {result_entry['vram_used_mb']} MB | System RAM: {result_entry['ram_used_gb']} GB")

        print("\n=========================================================================================")
        print("                                SUMMARY REPORT TABLE                                     ")
        print("=========================================================================================")
        print(f"{'ID':<15} | {'Lang':<8} | {'Tokens':<7} | {'TPS':<8} | {'Total(s)':<8} | {'VRAM(MB)':<8}")
        print("-" * 65)
        for r in results:
            vram_str = str(r['vram_used_mb']) if r['vram_used_mb'] is not None else "CPU"
            print(f"{r['id']:<15} | {r['language']:<8} | {r['tokens_generated']:<7} | {r['tokens_per_second']:<8} | {r['total_time_seconds']:<8} | {vram_str:<8}")
        print("=========================================================================================\n")

        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({"results": results, "settings": settings.model_dump(mode="json")}, f, indent=2)
            print(f"[+] Detailed benchmark results saved to {output_file}")

    finally:
        print("[*] Stopping server...")
        server_mgr.stop()

    return results


if __name__ == "__main__":
    low_res = "--low-resource" in sys.argv
    out_path = Path(__file__).resolve().parent.parent.parent / "docs" / "BENCHMARK_RESULTS.json"
    run_benchmark(low_resource=low_res, output_file=out_path)
