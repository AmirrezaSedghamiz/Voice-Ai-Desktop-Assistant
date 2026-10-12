# Reproducible Setup & Installation Guide

This guide documents the exact, verified setup procedure for running the **Resource-Constrained Local AI Assistant** on Windows 11 with NVIDIA GPU acceleration.

---

## 1. Prerequisites Verified on Target Machine

* **Operating System:** Windows 11 (64-bit).
* **RAM:** >= 16 GB (Host machine tested: 24 GB).
* **GPU:** NVIDIA GPU with >= 4 GB VRAM (Host machine tested: RTX 3050 Ti Laptop GPU).
* **NVIDIA Drivers:** Modern Game Ready / Studio driver with CUDA 12.x/13.x support.
* **Python Runtime:** Python 3.12 (specifically `3.12.x`; do **not** use experimental Python 3.14).

---

## 2. Fast Setup via Batch Launcher (`start.bat`)

The project includes an intelligent launcher (`start.bat`) that verifies all components and **guarantees zero redundant downloads**:

```cmd
cd "c:\Users\ACER\Desktop\AI voice assistant"
start.bat
```

* If `.venv` is missing, it creates it using Python 3.12.
* If dependencies are missing, it installs `requirements.txt`.
* If binaries or models are missing, it triggers the verified downloader.
* If all files are present, it **immediately launches without downloading anything**.

### Available Launcher Modes
```cmd
start.bat                  :: Starts the interactive Assistant CLI
start.bat --low-resource   :: Starts with throttled CPU threads and reduced GPU layers
start.bat --benchmark      :: Executes the automated latency & resource benchmark
start.bat --test           :: Executes the 12-test unit test suite
start.bat --docker         :: Launches the containerized environment via Docker Compose
```

---

## 3. Manual Step-by-Step Installation

If you prefer executing each step manually:

### Step 1: Create the Python 3.12 Virtual Environment
```powershell
# Explicitly use Python 3.12 (avoid default Python 3.14 on PATH)
& "C:\Users\ACER\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
```

### Step 2: Install Pinned Dependencies
```powershell
$env:NO_PROXY = "*"
& ".venv\Scripts\pip.exe" install -r requirements.txt
```

### Step 3: Download and Verify Local Assets
Run the verified downloader:
```powershell
& ".venv\Scripts\python.exe" scripts\download_assets.py
```
* **llama.cpp Binary:** Official release `b11429-bin-win-cuda-12.4-x64.zip` (SHA-256 verified).
* **CUDA Runtime DLLs:** Copied directly from local `CUDA\v12.9\bin` or downloaded.
* **Model:** `Qwen3-1.7B-Q4_K_M.gguf` from Hugging Face (SHA-256: `d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5`).

---

## 4. Running the Test Suite & Benchmarks

Verify all configuration boundaries and security gates:
```powershell
& ".venv\Scripts\pytest.exe" -v
```

Execute hardware latency benchmarks:
```powershell
& ".venv\Scripts\python.exe" -m src.eval.benchmark
```

---

## 5. Dockerized Deployment (Zero Redownload Guarantee)

To run via Docker Desktop while ensuring model files are **never** redownloaded:
```cmd
docker compose up --build
```
* The Dockerfile uses cached dependency layers.
* The 1.28 GB model is mounted read-only from `./models:/app/models:ro` on the host. Editing source code or rebuilding the image will never redownload model weights.

---

## 6. Complete Uninstallation / Rollback

To completely remove the setup and leave zero trace on the machine:
1. Remove firewall rules (if created):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\rollback_firewall.ps1
   ```
2. Delete the workspace folder:
   ```cmd
   rmdir /s /q "c:\Users\ACER\Desktop\AI voice assistant"
   ```
No global registry keys or system environment variables were modified during setup.
