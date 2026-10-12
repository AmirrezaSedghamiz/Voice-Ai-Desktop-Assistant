# Resource-Constrained Local Desktop AI Assistant

[![Windows 11](https://img.shields.io/badge/Platform-Windows%2011%20x64-0078D6?logo=windows)](docs/ENVIRONMENT_AUDIT.md)
[![Hardware](https://img.shields.io/badge/GPU-RTX%203050%20Ti%20(4GB)-76B900?logo=nvidia)](docs/RESOURCE_BUDGET.md)
[![Offline Security](https://img.shields.io/badge/Security-Genuine%20Offline%20Air--Gap-critical)](docs/SECURITY_AND_ISOLATION.md)
[![Voice Pipeline](https://img.shields.io/badge/Voice-Whisper%20STT%20%2B%20Piper%20TTS-blueviolet)](docs/MODEL_EVALUATION.md)
[![Memory Store](https://img.shields.io/badge/Memory-SQLite%20%2B%20FTS5%20(0%20MB%20VRAM)-blue)](docs/MEMORY_ARCHITECTURE.md)
[![Tests](https://img.shields.io/badge/Tests-47%20Passed%20(100%25)-success)](tests/)

An enterprise-grade, resource-governed, and genuine offline desktop AI assistant engineered for Windows systems with constrained hardware (e.g., 4 GB laptop GPUs).

Built with a modular Python architecture, high-performance CUDA `llama.cpp` inference, local CPU-based Speech-to-Text (`faster-whisper`), local neural Text-to-Speech (`piper-tts`), a zero-VRAM persistent SQLite + FTS5 memory store (`src/memory/store.py`), an independent Policy Engine, privacy-preserving audit logging, and strict operating-system-level firewall isolation.

---

## Cascaded Voice Architecture & Key Principles

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                           User Interaction                             │
  │     Microphone (Push-to-Talk / VAD)    │     Speaker Output            │
  └──────────────────┬─────────────────────┴─────────────▲─────────────────┘
                     │                                   │
                     ▼                                   │
  ┌──────────────────────────────────────┐               │
  │     Local Whisper STT (CPU INT8)     │               │
  │  - Faster-Whisper Multilingual Base  │               │
  │  - 0 MB VRAM, 4 threads, ~140 MB RAM │               │
  └──────────────────┬───────────────────┘               │
                     │ (Transcribed Text)                │
                     ▼                                   │
  ┌──────────────────────────────────────────────────────┴─────────────────┐
  │                         Orchestrator Engine                            │
  │     - Session State Management         - Concurrency Gate (max=1)      │
  │     - Resource Governor (below-normal) - Idle Watchdog (300s timeout)  │
  └──────────────────┬───────────────────────────────┬─────────────────────┘
                     │                               │
                     ▼                               ▼
  ┌──────────────────────────────────────┐   ┌─────────────────────────────┐
  │         Policy Engine & Safety       │   │     Audit & Redaction Log   │
  │  - Whitelisted structured actions    │   │  - Local file log           │
  │  - Rejects arbitrary shell/CMD       │   │  - Regex token/key scrub    │
  │  - Zero privilege escalation         │   │  - User privacy guaranteed  │
  └──────────────────┬───────────────────┘   └─────────────────────────────┘
                     │                               ▲
                     ▼                               │ (Final Response)
  ┌──────────────────────────────────────────────────┴─────────────────────┐
  │                      Offline Local Inference Layer                     │
  │  - llama.cpp CUDA Server (Loopback 127.0.0.1:8080)                    │
  │  - Qwen3-1.7B-Q4_K_M (1.46 GB VRAM, ~62 tokens/s generation)           │
  │  - CPU-only Fallback Mode (0 MB VRAM, ~19 tokens/s generation)         │
  └──────────────────┬─────────────────────────────────────────────────────┘
                     │ (Generated Response)
                     ▼
  ┌──────────────────────────────────────┐
  │      Local Piper TTS (CPU ONNX)      │
  │  - en_US-lessac-medium neural voice  │
  │  - 0 MB VRAM, RTF < 0.10, ~60 MB RAM ├───────────────┘
  └──────────────────────────────────────┘
```

1. **Genuine Offline Isolation:** No remote AI inference APIs, zero update checkers, and OS-level Windows Firewall outbound rules blocking all network egress.
2. **Resource Governance:** Inference runs at Windows `BELOW_NORMAL` process priority with capped CPU threads (4 threads) and 24 offloaded GPU layers. Over 2.4 GB of VRAM remains free on a 4 GB GPU for foreground desktop apps and gaming.
3. **Safe Agent Boundary:** The LLM does **not** possess shell access or unconstrained execution. It proposes structured actions that are validated and authorized by an independent, rule-based Policy Engine before execution.
4. **Zero Redundant Downloads:** Intelligent batch scripts (`start.bat`) and Docker volumes mount existing files on disk; assets are verified via SHA-256 hashes and downloaded only when missing.

---

## Target Hardware & Verified Baseline

Tested and benchmarked on a production Windows 11 mobile workstation:

| Component | Specification | Assistant Allocation / Behavior |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 Enterprise (Build 26200, 64-bit) | Standard Windows NT process priority & Defender Firewall |
| **CPU** | 12th Gen Intel Core i7-12700H (14 cores, 20 threads) | Budgeted to 4 threads; leaves 2 P-cores & all E-cores free |
| **System RAM** | 24 GB DDR5 | Assistant process consumes < 1.5 GB in RAM |
| **Dedicated GPU** | NVIDIA GeForce RTX 3050 Ti Laptop GPU (4 GB VRAM) | Consumes **~1,463 MiB VRAM**; leaves **> 2.4 GB free** |
| **Inference Runtime** | `llama.cpp` Windows CUDA build b11429 | Native CUDA acceleration with CPU fallback (`-ngl 0`) |
| **Primary Model** | `Qwen3-1.7B-Q4_K_M.gguf` (SHA-256 verified) | **60.5 – 63.5 tokens/sec** prompt generation speed |
| **STT Runtime** | `faster-whisper` Multilingual Base (CPU INT8) | **0 MB VRAM**, ~1.6s latency, 0% Word Error Rate |
| **TTS Runtime** | `piper-tts` ONNX `en_US-lessac-medium` (CPU) | **0 MB VRAM**, ~0.09s latency, RTF < 0.10 |

---

## Quick Start

### 1. Launch via Batch Script (`start.bat`)

The fastest way to launch the assistant. It automatically checks `.venv`, verifies dependencies, confirms model assets, and starts the session:

```cmd
cd "c:\Users\ACER\Desktop\AI voice assistant"
start.bat
```

#### Available Modes:
```cmd
start.bat                  :: Starts the interactive text CLI
start.bat --voice          :: Starts interactive VOICE mode (Push-to-Talk)
start.bat --voice --trigger-mode vad :: Starts VOICE mode with continuous VAD
start.bat --voice --no-tts :: Voice input (STT) with text-only responses
start.bat --download-voice :: Pre-provisions local STT and TTS models
start.bat --low-resource   :: Starts with throttled CPU threads and reduced GPU layers
start.bat --benchmark      :: Executes automated hardware & bilingual benchmarks
start.bat --test           :: Executes the 32-test unit test suite
start.bat --docker         :: Runs the assistant inside Docker with mounted volumes
```

### 2. Manual Environment Setup

If you prefer step-by-step terminal execution:

```powershell
# 1. Create virtual environment anchored to Python 3.12 (avoids experimental Python 3.14 on PATH)
& "C:\Users\ACER\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv

# 2. Install pinned dependencies (bypassing dead proxy if active)
$env:NO_PROXY = "*"
& ".venv\Scripts\pip.exe" install -r requirements.txt

# 3. Verify or download assets (GGUF model & llama.cpp binaries)
& ".venv\Scripts\python.exe" scripts\download_assets.py

# 4. Launch interactive CLI
& ".venv\Scripts\python.exe" -m src.cli
```

---

## Security & Firewall Outbound Isolation

To guarantee that the assistant cannot send telemetry, prompt logs, or data outbound, Windows Defender Firewall rules can be enforced:

### Enable Firewall Block (Run as Administrator)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\configure_firewall.ps1
```
This blocks all outbound WAN traffic for both `llama-server.exe` and `.venv\Scripts\python.exe` while maintaining loopback (`127.0.0.1`) IPC.

### Verify Offline Isolation
```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_offline.ps1
```

### Rollback Firewall Rules
```powershell
powershell -ExecutionPolicy Bypass -File scripts\rollback_firewall.ps1
```

For complete threat models and air-gap notes, see [`docs/SECURITY_AND_ISOLATION.md`](docs/SECURITY_AND_ISOLATION.md).

---

## Resource Governor & Performance

The assistant enforces strict hardware budgets:

* **Process Priority:** Set to `BELOW_NORMAL` via `psutil`. The Windows scheduler immediately prioritizes user typing, web browsing, and foreground applications.
* **GPU Memory Footprint:** Fixed at ~1,463 MiB VRAM. Leaves 58% of dedicated GPU memory free for other apps.
* **Idle Watchdog:** Automatically shuts down the local inference server after 300 seconds of inactivity to return all memory to the operating system.
* **CPU-Only Fallback:** If the GPU is fully occupied (e.g., during 3D gaming), setting `gpu_layers=0` yields **~18.8 tokens/sec** on CPU with **0 MB VRAM** usage.

### Empirical Benchmarks (`docs/BENCHMARK_RESULTS.json`)

| Benchmark Prompt | Language | Throughput | Latency | VRAM Used |
| :--- | :--- | :--- | :--- | :--- |
| **Short Factual Query** | English | **60.48 tok/s** | 2.94 s | 1,462 MiB |
| **Logical Reasoning & Structure** | English | **63.26 tok/s** | 8.09 s | 1,463 MiB |
| **Factual Comprehension** | Persian (فارسی) | **61.48 tok/s** | 3.45 s | 1,463 MiB |
| **Technical Vocabulary** | Persian (فارسی) | **63.48 tok/s** | 8.07 s | 1,463 MiB |

Detailed telemetry is documented in [`docs/RESOURCE_BUDGET.md`](docs/RESOURCE_BUDGET.md) and [`docs/MODEL_EVALUATION.md`](docs/MODEL_EVALUATION.md).

---

## Safe Agent Architecture & Tool Execution

The assistant implements an independent Policy Engine (`src/agent/policy_engine.py`):
* **Untrusted LLM Output:** Text generated by the model is treated as untrusted proposals.
* **Whitelisted Actions:** Only registered tools with strict schemas can be proposed.
  * System diagnostics (`system_status`, `battery_status`, `storage_info`)
  * Approved application launching (`notepad`, `calculator`)
* **Strict Blacklist:** Arbitrary shell commands (`powershell`, `cmd`, `bash`, `rm`, `del`, `format`, `curl`, `netsh`) are unconditionally rejected by the Policy Engine before execution.
* **Audit Logging:** Every proposed action, authorization verdict, and tool execution is recorded in `logs/audit.jsonl` with automatic regex redaction of sensitive credentials.

---

## Running the Automated Test Suite

The project includes unit tests for configuration validation, policy boundaries, audit log redaction, and resource governance:

```cmd
start.bat --test
```
or via PowerShell:
```powershell
& ".venv\Scripts\pytest.exe" -v
```

All 12 tests execute in under 0.5 seconds without requiring an active GPU or network connection.

---

## Project Structure

```
AI voice assistant/
├── bin/
│   └── llama.cpp/            # Portable Windows CUDA inference binaries & DLLs
├── docs/
│   ├── BENCHMARK_RESULTS.json # Raw benchmark measurements
│   ├── ENVIRONMENT_AUDIT.md   # Initial hardware & environment discovery audit
│   ├── MODEL_EVALUATION.md    # Model architecture, quantization & bilingual review
│   ├── RESOURCE_BUDGET.md     # Resource governor specification & telemetry
│   ├── SECURITY_AND_ISOLATION.md # Threat model, firewall policies & air-gap guide
│   ├── SETUP_GUIDE.md         # Reproducible manual installation steps
│   └── TROUBLESHOOTING.md     # Real-world diagnostics and edge-case fixes
├── models/
│   └── Qwen3-1.7B-Q4_K_M.gguf # Primary local GGUF model (SHA-256 verified)
├── scripts/
│   ├── configure_firewall.ps1 # Creates outbound block rules in Windows Firewall
│   ├── download_assets.py     # Verified downloader with Range resume & retry
│   ├── rollback_firewall.ps1  # Safely removes project firewall rules
│   └── verify_offline.ps1     # Tests loopback binding & verifies WAN egress is blocked
├── src/
│   ├── adapter/               # llama.cpp server supervisor & HTTP client
│   ├── agent/                 # Policy engine, orchestrator, and audit logging
│   ├── core/                  # Pydantic configuration schemas & resource governor
│   ├── eval/                  # Benchmark suite & telemetry collectors
│   └── cli.py                 # Interactive diagnostic command-line interface
├── tests/                     # Pytest suite (12 tests)
├── .env.example               # Configuration template
├── Dockerfile                 # Containerized deployment with CUDA runtime
├── docker-compose.yml         # Compose specification with volume mounts
├── requirements.txt           # Pinned Python package dependencies
└── start.bat                  # Smart Windows launcher
```

---

## Future Roadmap (Speech Pipeline)

As agreed during architecture planning, the assistant follows a **cascaded speech architecture**:
1. **Speech-to-Text (STT):** Local Whisper (`whisper.cpp` or `faster-whisper` quantized to INT8).
2. **Reasoning Core (LLM):** Qwen3 local inference (established in this repository).
3. **Text-to-Speech (TTS):** Local Piper TTS (`piper-tts` ONNX).

This modular pipeline ensures transparent testing, independent component debugging, and minimal memory contention compared to monolithic end-to-end audio models.
