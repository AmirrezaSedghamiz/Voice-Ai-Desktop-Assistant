# Troubleshooting & Diagnostic Guide

This document captures real-world edge cases, errors, diagnostic steps, and verified solutions discovered while establishing the **Resource-Constrained Local AI Assistant** on Windows 11.

---

## 1. Quick Diagnostic Checklist

Before diving into specific errors, run the diagnostic suite:

```cmd
:: 1. Run the test suite (12 tests)
start.bat --test

:: 2. Verify offline status and loopback binding
powershell -ExecutionPolicy Bypass -File scripts\verify_offline.ps1

:: 3. Check live GPU VRAM usage and active processes
nvidia-smi
```

---

## 2. Common Failure Scenarios & Resolutions

### Scenario A: Stale Windows Proxy (`WinError 10061`)
* **Symptom:** During dependency installation or initial asset download, Python or pip fails with:
  ```text
  urllib.error.URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
  ```
  or connection attempts route to a dead port like `127.0.0.1:60213`.
* **Root Cause:** A VPN client, corporate proxy, or previous local proxy left `ProxyEnable=1` configured in the Windows Internet Settings registry (`HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings`).
* **Resolution:**
  1. For pip in PowerShell:
     ```powershell
     $env:NO_PROXY = "*"
     & ".venv\Scripts\pip.exe" install -r requirements.txt
     ```
  2. For Python scripts: Use an explicit empty proxy handler:
     ```python
     import urllib.request
     opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
     urllib.request.install_opener(opener)
     ```
  3. In `httpx.Client`, explicitly specify `trust_env=False` so loopback `127.0.0.1` traffic is never proxied.

---

### Scenario B: Default Python 3.14 Collision on Windows PATH
* **Symptom:** Creating `.venv` or compiling packages produces missing wheel errors or C-extension syntax failures.
* **Root Cause:** Python 3.14 (an experimental alpha build) is present in the global Windows `PATH` (`C:\Python314\python.exe`). PyTorch, NumPy, and Pydantic binary wheels do not yet support Python 3.14.
* **Resolution:** Always invoke Python 3.12 explicitly:
  ```cmd
  py -3.12 -m venv .venv
  :: Or directly via full path:
  "C:\Users\ACER\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
  ```
  The provided `start.bat` launcher handles this detection automatically.

---

### Scenario C: CUDA Runtime DLL Linking Error (`cudart64_12.dll`)
* **Symptom:** `llama-server.exe` fails to start with:
  ```text
  The code execution cannot proceed because cudart64_12.dll was not found.
  ```
  or silently falls back to CPU execution.
* **Root Cause:** The portable `llama.cpp` Windows CUDA binaries dynamically link against CUDA 12.x runtime DLLs (`cudart64_12.dll`, `cublas64_12.dll`, `cublasLt64_12.dll`), which may not be present in `PATH`.
* **Resolution:**
  The target host already possesses CUDA Toolkit 12.9 installed at:
  `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin`
  Copy the three required runtime DLLs directly into `bin\llama.cpp\`:
  ```powershell
  $cudaBin = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin"
  Copy-Item "$cudaBin\cudart64_12.dll" "bin\llama.cpp\"
  Copy-Item "$cudaBin\cublas64_12.dll" "bin\llama.cpp\"
  Copy-Item "$cudaBin\cublasLt64_12.dll" "bin\llama.cpp\"
  ```

---

### Scenario D: Console Encoding Error with Persian Text (`cp1252`)
* **Symptom:** Printing benchmark results or chat responses containing Persian characters throws:
  ```text
  UnicodeEncodeError: 'charmap' codec can't encode characters in position ...
  ```
* **Root Cause:** The default Windows command console code page is legacy Windows-1252 (`cp1252`), which cannot represent the Perso-Arabic unicode block.
* **Resolution:**
  1. In Python entry point scripts, force stdout to UTF-8:
     ```python
     import sys
     sys.stdout.reconfigure(encoding="utf-8")
     ```
  2. In Windows batch files (`start.bat`), switch code page before launching:
     ```cmd
     chcp 65001 >nul
     ```

---

### Scenario E: Large Model Download Disconnection / Mid-Stream Drops
* **Symptom:** Downloading the 1.2 GB GGUF model fails after 400–600 MB due to transient connection drops or rate-limiting.
* **Root Cause:** Standard Python `urllib.request.urlretrieve` re-downloads the entire file from byte 0 on failure.
* **Resolution:** `scripts/download_assets.py` includes HTTP Range resume (`Range: bytes={existing}-`) and an automatic 15x exponential backoff retry loop. Simply re-run `start.bat` or `python scripts/download_assets.py`; it will resume from the exact byte where it paused.

---

### Scenario F: Non-Interactive Subprocess Hang in `llama.cpp`
* **Symptom:** When spawned from Python or a script, `llama-cli.exe` hangs indefinitely or throws an EOF read error.
* **Root Cause:** In modern `llama.cpp` builds, the CLI defaults to interactive REPL mode unless explicit non-interactive flags are supplied.
* **Resolution:** Always pass `--simple-io` when invoking `llama-cli.exe` in subprocesses:
  ```powershell
  bin\llama.cpp\llama-cli.exe -m models\Qwen3-1.7B-Q4_K_M.gguf -p "Hello" -n 32 --simple-io
  ```

---

### Scenario G: GPU Contention or Desktop Hitching During Heavy Gaming
* **Symptom:** User is running a 3D game or rendering video on the RTX 3050 Ti, and the assistant causes frame rate drops.
* **Root Cause:** The RTX 3050 Ti has 4 GB total VRAM. If a game allocates 3.5 GB and the assistant attempts to allocate 1.46 GB, Windows WDDM will page memory to system RAM, causing micro-stutters.
* **Resolution:**
  1. Switch to Low-Resource Mode:
     ```cmd
     start.bat --low-resource
     ```
  2. Or switch to 100% CPU-only mode by setting `GPU_LAYERS=0` in `.env`:
     ```env
     GPU_LAYERS=0
     ```
     CPU inference will run at **~18.8 tokens/sec** with zero GPU load.

---

### Scenario H: Firewall Script Permission Denied
* **Symptom:** `scripts\configure_firewall.ps1` returns `Access is denied (Exception from HRESULT: 0x80070005)`.
* **Root Cause:** Creating Windows Defender Firewall rules requires elevated administrative privileges.
* **Resolution:** Right-click PowerShell or Windows Terminal, select **"Run as Administrator"**, and run:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\configure_firewall.ps1
  ```

---

### Scenario I: Microphone Access or Audio Device Disconnected
* **Symptom:** Voice mode launches, but fails with `sounddevice.PortAudioError: Invalid number of channels` or `RuntimeError: No default input device`.
* **Root Cause:** Windows Microphone Privacy Settings may have restricted desktop app access, or the laptop's internal microphone array is muted/disabled.
* **Resolution:**
  1. Open Windows Settings $\to$ Privacy & Security $\to$ Microphone. Ensure **"Let desktop apps access your microphone"** is set to **On**.
  2. To list available hardware input devices:
     ```powershell
     & ".venv\Scripts\python.exe" -c "import sounddevice as sd; print(sd.query_devices())"
     ```
  3. You can specify a custom input or output device index in `AudioConfig` or via environment variables.

---

### Scenario J: Voice Models Missing or Corrupted
* **Symptom:** Starting voice mode prints `[ERROR] Required voice models not found`.
* **Root Cause:** The STT (`whisper-base`) or TTS (`en_US-lessac-medium`) models were not provisioned during setup.
* **Resolution:**
  Run the idempotent voice model downloader:
  ```cmd
  start.bat --download-voice
  :: Or directly in PowerShell:
  & ".venv\Scripts\python.exe" scripts\download_assets.py --voice
  ```
  The script will verify existing files and download any missing models with cryptographic SHA-256 checks.

