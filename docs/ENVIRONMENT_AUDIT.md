# Environment Audit & Baseline Report

**Audit Timestamp:** 2026-10-12T20:56:00+03:30  
**Target Host:** ACER Windows Workstation  
**Auditor:** Systems & Local-LLM Engineering  

---

## 1. Operating System & Hardware

| Parameter | Observed Value | Assessment / Implications |
| :--- | :--- | :--- |
| **Operating System** | Microsoft Windows 11 Enterprise | Modern desktop OS supporting WDDM 3.x and Windows Firewall automation |
| **OS Build / Version** | 10.0.26200 (Build 26200, 64-bit) | Recent build supporting standard PowerShell 5.1/7+, process priority controls |
| **CPU** | 12th Gen Intel(R) Core(TM) i7-12700H | Heterogeneous architecture: 14 physical cores (6 P-cores + 8 E-cores), 20 logical threads |
| **Physical Memory (RAM)** | 23.71 GB Usable (~25.46 GB Total) | Ample headroom to run 1.7B/4B models in RAM, but must budget <= 6 GB for assistant |
| **Storage (System & Workspace)**| Drive C: 72.08 GB Free (out of 456.48 GB) | Ample disk capacity for GGUF models (~1.2 - 2.5 GB) and runtime binaries (~650 MB) |
| **Secondary Partitions** | D: 3.66 GB Free, E: 1.24 GB Free, F: 27.68 GB Free, G: 97.78 GB Free | Drive G: is available as an auxiliary storage option if model library expands |

---

## 2. GPU & Graphics Subsystem

| Parameter | Observed Value | Assessment / Implications |
| :--- | :--- | :--- |
| **Dedicated GPU** | NVIDIA GeForce RTX 3050 Ti Laptop GPU | Mobile Ampere architecture (Compute Capability 8.6) |
| **Dedicated VRAM** | 4096 MiB (4.0 GB GDDR6) | **Strict Constraint:** Total VRAM is tight. Must reserve >= 750 MiB for desktop/apps |
| **Driver Version** | 32.0.16.1062 (NVIDIA Driver 610.62) | Modern driver supporting CUDA 13.x and 12.x runtimes |
| **CUDA UMD Version** | 13.3 | Compatible with CUDA 12.x forward-compatibility runtimes |
| **Integrated GPU** | Intel(R) Iris(R) Xe Graphics (1 GB shared) | Handles secondary display outputs |
| **nvidia-smi Status** | Functional (`C:\Windows\System32\nvidia-smi.exe`) | Active, provides telemetry on power, temperature, and memory |
| **Current VRAM Usage** | ~229 MiB Used / 3867 MiB Free | Low baseline usage |
| **Thermal / Power Envelope**| 8W current / 75W Cap, Temp 57°C | Heavy inference will produce heat and fan noise; burst throttling is required |

### Competing GPU Processes Detected
At the time of audit, the following desktop applications hold handles on the NVIDIA GPU:
- `TextInputHost.exe`, `SearchHost.exe`, `StartMenuExperienceHost.exe` (Windows Shell)
- `MarkdownMonster.exe` (Editor)
- `Docker Desktop.exe` (Container UI background)
- `Antigravity.exe` (IDE)
- `msedgewebview2.exe` (Web runtime)
- `EdgeGameAssist.exe` (Browser overlay)
- `Cloudflare WARP.exe` (VPN client)
- `WindowsTerminal.exe` (Terminal emulator)
- `Telegram.exe` (Messaging client)

*Assessment:* These applications consume ~229 MiB VRAM. When running games, heavy 3D rendering, or large browser tabs, VRAM availability will fluctuate. Over-allocating GPU layers will cause WDDM to spill tensors into shared system RAM, resulting in severe frame stuttering. The resource governor must allow dynamic CPU fallback.

---

## 3. Python Ecosystem & Tooling Analysis

| Executable Path | Version | Current PATH State | Risk & Recommendation |
| :--- | :--- | :--- | :--- |
| `C:\Python314\python.exe` | **Python 3.14.7** | **Active Default in PATH** | **CRITICAL RISK:** Python 3.14 is an experimental alpha/dev build. Almost no C-extension binary wheels (PyTorch, llama-cpp-python, NumPy, pydantic-core) exist for Windows on 3.14. **Do NOT use for project virtual environment.** |
| `C:\Users\ACER\AppData\Local\Programs\Python\Python312\python.exe` | **Python 3.12.10** | Present on disk, registered in Windows `py` launcher | **RECOMMENDED FOUNDATION:** Stable, LTS ecosystem support, pre-built binary wheels available for all required packages. Project `.venv` will be explicitly anchored to this binary. |
| `C:\Users\ACER\AppData\Local\Programs\Python\Python311\python.exe` | **Python 3.11.5** | Present in PATH | Secondary stable fallback option. |

### Package Managers Detected
- `pip`: Installed for Python 3.14 and 3.11.
- `uv`: Not present in PATH.
- `poetry`: Not present in PATH.
- `conda`: Not present in PATH.

---

## 4. Local AI & CUDA Infrastructure

| Component | Status | Details |
| :--- | :--- | :--- |
| **CUDA Toolkit** | Installed (`v12.9`) | Located at `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9`. Compiler `nvcc` V12.9.86 present. (Bin directory not in PATH). |
| **Ollama** | Installed | Binary present at `C:\Users\ACER\AppData\Local\Programs\Ollama\ollama.exe`. Service is **not running**. `~/.ollama/models` contains 1.33 GB of embedding models (`bge-m3:latest`, `nomic-embed-text:latest`). No LLM models downloaded. |
| **llama.cpp** | Not installed in PATH | No global `llama-cli.exe` or `llama-server.exe`. |
| **LM Studio** | Not installed | AppData and Programs directories checked; absent. |
| **Hugging Face Cache**| Clean | No cache detected at `~/.cache/huggingface`. |

---

## 5. Potential Conflicts & Mitigations

1. **Default Python 3.14 Collision:**
   - *Issue:* Executing `python` without qualification invokes Python 3.14.
   - *Mitigation:* Explicitly spawn the project environment using `& 'C:\Users\ACER\AppData\Local\Programs\Python\Python312\python.exe' -m venv .venv`. Inside the project, all tooling invokes `.venv\Scripts\python.exe` directly.
2. **GPU VRAM Ceiling (4 GB):**
   - *Issue:* RTX 3050 Ti has only 4 GB VRAM. Model weights + KV cache can easily exceed 4 GB if using unquantized weights or large models (e.g. 7B/8B).
   - *Mitigation:* Use 1.7B (Q4_K_M ~1.2 GB) or 4B (Q4_K_M ~2.5 GB) with context strictly bounded to 2,048 tokens. Offload only safe layer counts (`-ngl 24` for 1.7B), leaving >= 1.5 GB VRAM free.
3. **CPU Priority & Latency:**
   - *Issue:* 14-core i7-12700H has 6 P-cores and 8 E-cores. Unconstrained thread pools can starve foreground tasks.
   - *Mitigation:* Cap `llama.cpp` CPU threads to 4 or 6. Set inference worker process priority to `BELOW_NORMAL_PRIORITY_CLASS`.
4. **Network Access Control:**
   - *Issue:* Windows apps have outbound network access by default.
   - *Mitigation:* Explicit Windows Firewall outbound block rule targeted to the exact executable path of `llama-server.exe` and `.venv\Scripts\python.exe`.
