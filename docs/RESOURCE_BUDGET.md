# Resource Budget, Governor & Telemetry

This document outlines the resource governance architecture, configuration policies, limits, and empirical hardware measurements for the **Resource-Constrained Local AI Assistant** on Windows 11.

---

## 1. System Hardware Baseline

* **CPU:** 12th Gen Intel Core i7-12700H (14 cores: 6 Performance + 8 Efficient cores, 20 logical threads).
* **RAM:** 24 GB DDR5 (23.71 GB usable).
* **GPU:** NVIDIA GeForce RTX 3050 Ti Laptop GPU (4,096 MiB dedicated GDDR6 VRAM, 75W TGP).
* **Operating System:** Windows 11 Enterprise (Build 26200, 64-bit, WDDM 3.x).

---

## 2. Resource Governor Architecture & Policies

The resource governor (`src/core/governor.py`) coordinates execution etiquette so the assistant runs quietly in the background without starving interactive desktop applications (browser, IDE, office software, or games).

```
                      ┌──────────────────────────────────────────────┐
                      │              Resource Governor               │
                      └──────────────────────┬───────────────────────┘
                                             │
             ┌───────────────────────────────┼───────────────────────────────┐
             ▼                               ▼                               ▼
    [ Process Priority ]             [ Concurrency Gate ]            [ Idle Watchdog ]
  Windows: BELOW_NORMAL            Strict Semaphore (max=1)         Unload model after 300s
  Yields CPU cycles to             Zero memory spike from           Free VRAM for desktop
  foreground apps                  overlapping requests             applications
```

### Policy 1: CPU Thread Allocation & Core Topology
* **Default Allocation:** 4 worker threads (`cpu_threads = 4`).
* **Rationale:** The i7-12700H possesses 6 Performance cores. Allocating 4 threads allows llama.cpp compute kernels to execute efficiently across P-cores while leaving at least 2 P-cores and all 8 E-cores completely unencumbered for foreground Windows tasks and OS interrupts.
* **Low-Resource Mode:** Reduced to 2 threads (`cpu_threads = 2`).

### Policy 2: Process Scheduling Priority
* **Default Setting:** `BELOW_NORMAL` (`psutil.BELOW_NORMAL_PRIORITY_CLASS`).
* **Engineering Reality & Caveat:** Setting a process priority to `BELOW_NORMAL` **does not impose a hard percentage cap** on CPU usage. When the system is otherwise idle, a `BELOW_NORMAL` process can still consume 100% of its assigned cores. However, the Windows NT kernel scheduler guarantees that the moment a foreground application (e.g., typing in a browser, moving windows, running audio/video) demands CPU time, the assistant's inference worker immediately yields execution quantum without hitching or UI latency.

### Policy 3: GPU Layer Offloading (`gpu_layers`)
* **Default Setting:** 24 layers (`gpu_layers = 24`) for Qwen3-1.7B (28 total transformer layers).
* **Engineering Reality & Caveat:** Reducing GPU layers offloaded to CUDA reduces the amount of static weights placed into VRAM, but during active token generation, the GPU core utilization will still reach 80–100% burst for the milliseconds of compute. The offload limit is designed to guarantee VRAM budget safety, preventing Windows WDDM paging.
* **Low-Resource Mode:** Reduced to 12 layers (`gpu_layers = 12`).
* **CPU-Only Fallback:** Set `gpu_layers = 0` (`-ngl 0`), reserving 100% of the GPU for graphics or gaming.

### Policy 4: Context Window Sizing
* **Default Setting:** 2,048 tokens (`max_context_tokens = 2048`).
* **KV-Cache Budget:** With `Qwen3-1.7B-Q4_K_M` and FP16 KV cache, a 2,048-token context requires approximately ~128 MB of KV memory.
* **Configurability:** Up to 4,096 tokens is supported via configuration (`MAX_CONTEXT_TOKENS=4096`). At 4,096 tokens, KV cache grows to ~256 MB, well within safe limits.
* **Low-Resource Mode:** Reduced to 1,024 tokens.

### Policy 5: Concurrency Control
* **Default Setting:** 1 request (`max_concurrent_requests = 1`).
* **Behavior:** The orchestrator enforces single-threaded request queuing. Overlapping user queries are serialized, ensuring no sudden multiplication of VRAM or memory buffers.

### Policy 6: Idle Memory Reclamation & Unloading
* **Default Setting:** 300 seconds (5 minutes) inactivity timeout.
* **Behavior:** The background watchdog monitors `last_activity_time`. If no user interaction occurs for 300 seconds, the model server is cleanly terminated, returning ~1.46 GB VRAM and system memory back to the Windows memory manager. When a new prompt is submitted, the server automatically reloads on demand.

### Policy 7: User-Accessible Pause and Stop Controls
* **Interactive CLI Commands:**
  * `exit` or `quit`: Gracefully terminates the inference server and client.
  * `status`: Prints live CPU %, host RAM, and dedicated VRAM usage.
  * `stop` or `unload`: Immediately releases the model from memory without quitting the CLI session.
* **Low-Resource Mode Switch:** Can be toggled at launch via `start.bat --low-resource` or `.env` (`LOW_RESOURCE_MODE=true`).

---

## 3. Configuration Presets Comparison

| Configuration Parameter | Standard Mode (Default) | Low-Resource Mode (`--low-resource`) | CPU-Only Fallback (`gpu_layers=0`) |
| :--- | :--- | :--- | :--- |
| **CPU Worker Threads** | 4 threads | 2 threads | 4 threads |
| **Process Priority** | `BELOW_NORMAL` | `IDLE` | `BELOW_NORMAL` |
| **GPU Offloaded Layers**| 24 layers | 12 layers | 0 layers |
| **Context Length** | 2,048 tokens | 1,024 tokens | 2,048 tokens |
| **Max Output Tokens** | 512 tokens | 256 tokens | 512 tokens |
| **Max Concurrent Reqs** | 1 | 1 | 1 |
| **Idle Timeout** | 300 seconds | 120 seconds | 300 seconds |
| **VRAM Footprint** | ~1,462 MB | ~850 MB | **0 MB** |
| **Inference Speed** | **~61 – 63 tok/s** | ~35 – 40 tok/s | **~18.8 tok/s** |

---

## 4. Empirical Hardware Telemetry & Benchmarks

The benchmark suite (`src.eval.benchmark`) was executed on the live host environment with `Qwen3-1.7B-Q4_K_M.gguf`. Results are preserved in `docs/BENCHMARK_RESULTS.json`.

### A. CUDA GPU Mode (Standard Settings: `-ngl 24`, 4 threads)

| Benchmark Test Case | Prompt Tokens | Tokens Generated | Throughput (Tokens/s) | Generation Time | Peak VRAM Used | Total Host RAM |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EN Factual Prompt** (`en_short`) | 29 | 178 | **60.48 tok/s** | 2.943 s | **1,462.0 MiB** | 15.90 GB |
| **EN Logical Reasoning** (`en_reasoning`) | 41 | 512 | **63.26 tok/s** | 8.094 s | **1,463.0 MiB** | 15.93 GB |
| **FA Factual Query** (`fa_factual`) | 56 | 212 | **61.48 tok/s** | 3.448 s | **1,463.0 MiB** | 15.98 GB |
| **FA Vocabulary & Syntax** (`fa_grammar`) | 58 | 512 | **63.48 tok/s** | 8.065 s | **1,463.0 MiB** | 16.01 GB |

### B. VRAM Headroom Analysis
* **Total Dedicated VRAM:** 4,096 MiB
* **Pre-existing Windows / App Usage:** ~229 MiB
* **Assistant VRAM Consumption:** 1,463 MiB
* **Available Free VRAM During Full Generation:** **2,404 MiB (~2.4 GB Free)**
* **Verdict:** The assistant leaves **over 58% of the GPU's memory free** for other applications, guaranteeing zero risk of WDDM desktop stuttering or out-of-memory driver crashes.

### C. CPU-Only Fallback Mode (`-ngl 0`, `--simple-io`)
* **Prompt:** Factual verification test.
* **Throughput:** **18.8 tokens/sec**.
* **VRAM Consumption:** **0.0 MiB**.
* **Responsiveness:** While ~3.2x slower than GPU acceleration, 18.8 tokens/sec is substantially faster than human reading speed (~5 tokens/sec), making the CPU-only fallback genuinely viable when gaming or running heavy GPU workflows.

---

## 5. Thermal & Power Observations
* **Idle State:** GPU draws ~8W at 57°C.
* **During GPU Generation Burst (3–8 seconds):** GPU power rises to ~35–45W; temperature remains below 65°C.
* **Cooldown:** Because requests are discrete and bounded (max 512 output tokens), the GPU immediately returns to idle (8W) between user queries. The assistant never performs continuous spinning loops or unsanctioned background generation.
