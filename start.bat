@echo off
setlocal enabledelayedexpansion

title AI Assistant Launcher - Local ^& Offline

echo ========================================================
echo       Resource-Constrained Local AI Assistant
echo ========================================================
echo.

cd /d "%~dp0"

REM 1. Check or initialize Python virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [*] Initializing project-local virtual environment...
    py -3.12 -m venv .venv 2>nul
    if errorlevel 1 (
        echo [!] py -3.12 launcher not available. Trying direct path...
        "C:\Users\ACER\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
        if errorlevel 1 (
            echo [ERROR] Could not find Python 3.12 to create .venv.
            pause
            exit /b 1
        )
    )
    echo [+] Virtual environment created.
)

REM 2. Check dependencies (only install if marker missing - no redundant pip work)
if not exist ".venv\Lib\site-packages\pydantic" (
    echo [*] Installing pinned dependencies...
    set "NO_PROXY=*"
    set "HTTP_PROXY="
    set "HTTPS_PROXY="
    .venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

REM 3. Check assets (zero redundant download guarantee)
set "NEED_DOWNLOAD=0"
if not exist "bin\llama.cpp\llama-server.exe" set "NEED_DOWNLOAD=1"
if not exist "bin\llama.cpp\cudart64_12.dll" set "NEED_DOWNLOAD=1"
if not exist "models\Qwen3-1.7B-Q4_K_M.gguf" set "NEED_DOWNLOAD=1"

if "%NEED_DOWNLOAD%"=="1" (
    echo [*] Required local runtime or model file is missing.
    echo [*] Running asset downloader...
    set "NO_PROXY=*"
    set "HTTP_PROXY="
    set "HTTPS_PROXY="
    .venv\Scripts\python.exe scripts\download_assets.py
    if errorlevel 1 (
        echo [ERROR] Asset download failed. Check network connection and retry.
        pause
        exit /b 1
    )
) else (
    echo [OK] Runtime binaries and model already present. Zero downloads required.
)

echo.
REM 4. Handle command arguments
if "%1"=="--test" (
    echo [*] Running test suite...
    .venv\Scripts\pytest.exe -v
    goto :end
)

if "%1"=="--benchmark" (
    echo [*] Running resource and latency benchmarks...
    .venv\Scripts\python.exe -m src.eval.benchmark
    goto :end
)

if "%1"=="--docker" (
    echo [*] Launching via Docker Compose (using volume-mounted models)...
    docker compose up --build
    goto :end
)

if "%1"=="--low-resource" (
    echo [*] Starting assistant in LOW-RESOURCE mode (CPU priority below normal, 2 threads)...
    .venv\Scripts\python.exe -m src.cli --low-resource
    goto :end
)

REM Default: Interactive CLI
echo [*] Starting Assistant Interactive CLI...
.venv\Scripts\python.exe -m src.cli %*

:end
if errorlevel 1 pause
endlocal
