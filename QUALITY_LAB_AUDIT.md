# Quality Lab Audit: David Local Windows AI Assistant

**Date:** October 2026  
**Auditor:** Quality Lab Infrastructure & AI Evaluation Team  
**Scope:** Repository audit, architectural mapping, test gap analysis, and Quality Lab design specification.

---

## 1. Executive Summary

David is a fully local, resource-constrained desktop AI voice assistant built for Windows 10/11 x64. It is designed to run 100% offline with zero external network connectivity, utilizing quantized local neural models for language understanding, speech-to-text, text-to-speech, and keyword spotting.

This audit evaluates the codebase prior to the implementation of the comprehensive Quality Lab. It documents existing interfaces, dependency boundaries, testing infrastructure, hardware and model footprints, observed testing gaps, and architectural decisions for the Quality Lab.

---

## 2. Repository Structure & Entry Points

### 2.1 Workspace Layout
```
AI voice assistant/
├── bin/
│   └── llama.cpp/          # Native Windows x64 llama-server and CUDA/CPU DLLs
├── assets/                 # Icons and desktop application assets
├── data/                   # Runtime SQLite databases (assistant_memory.db, tasks.db) and logs
├── dist/                   # PyInstaller release distribution (david_assistant/)
├── docs/                   # Architecture, isolation, benchmark, and setup documentation
├── models/
│   ├── Qwen3-1.7B-Q4_K_M.gguf                     # Primary LLM GGUF (1.28 GB)
│   ├── stt/whisper-base/                          # faster-whisper INT8 CTranslate2 model
│   ├── tts/en_US-lessac-medium.onnx (+ .json)     # Piper neural voice ONNX model
│   └── wake_word/vosk-model-small-en-us-0.15/     # Offline Kaldi keyword acoustic model
├── scripts/
│   ├── download_assets.py   # Offline asset provisioning script
│   ├── package_release.py   # PyInstaller packaging script
│   └── verify_offline.ps1   # PowerShell network isolation check
├── src/
│   ├── adapter/             # LlamaServerManager & LocalLlmClient (loopback HTTP)
│   ├── agent/               # SafeAgentOrchestrator, PolicyEngine, AuditLogger
│   │   └── tools/           # ToolRegistry, TaskManager, ReminderScheduler, handlers
│   ├── audio/               # VoiceSessionManager, STT, TTS, WakeWordDetector, Recorder, Playback
│   ├── core/                # AssistantSettings, ResourceGovernor
│   ├── eval/                # Legacy latency/throughput benchmark script
│   ├── memory/              # SQLite + FTS5 persistent memory store
│   └── ui/                  # PySide6 desktop UI (MainWindow, workers, tray, widgets)
├── tests/                   # Existing pytest unit and component tests (94 tests)
├── david_assistant.spec     # PyInstaller onedir specification
├── pytest.ini               # pytest pythonpath and testpaths configuration
├── requirements.txt         # Production runtime dependencies
└── run_gui.py               # Desktop GUI application launcher
```

### 2.2 Application Entry Points
1. `run_gui.py`: Desktop graphical interface launcher via PySide6 (`src.ui.app.main()`).
2. `src/cli.py`: Interactive CLI with text chat, Push-to-Talk (PTT), Voice Activity Detection (VAD), and hardware telemetry display.
3. `src/eval/benchmark.py`: Standalone latency, throughput (tokens/sec), and resource consumption benchmark script.

---

## 3. Subsystem Architecture & Interface Contracts

```mermaid
graph TD
    UserVoice[Microphone Audio] --> WakeWord[WakeWordDetector (Vosk)]
    WakeWord -->|Keyword Spotted| VoiceSession[VoiceSessionManager]
    UserVoice -->|VAD / PTT| Recorder[AudioRecorder] --> VoiceSession
    VoiceSession --> STT[WhisperSttEngine (faster-whisper)]
    STT -->|Transcript| Orchestrator[SafeAgentOrchestrator]
    GUI[PySide6 MainWindow] -->|Text / Signals| Orchestrator
    Orchestrator --> Policy[PolicyEngine Gate]
    Policy -->|Permitted| ToolRegistry[SafeToolRegistry]
    Policy -->|Blocked| BlockNotice[Security Policy Block]
    ToolRegistry --> Handlers[App/Tasks/Files/Memory Handlers]
    Handlers --> Memory[MemoryStore (SQLite FTS5)]
    Handlers --> TasksDB[TaskManager (SQLite)]
    Orchestrator --> LLMClient[LocalLlmClient]
    LLMClient -->|HTTP 127.0.0.1| LlamaServer[llama-server.exe (Qwen3-1.7B)]
    Governor[ResourceGovernor] -->|Priority / Idle Unload| LlamaServer
    Orchestrator -->|Response Text| TTS[PiperTtsEngine (Piper ONNX)]
    TTS --> Playback[AudioPlaybackEngine (sounddevice)]
```

### 3.1 Interface Contracts
- **LLM Client & Server:** Local loopback HTTP (`127.0.0.1:8080/v1/chat/completions`). Request validation forbids non-loopback IPs. Emits token-by-token or single-turn completions with `InferenceMetrics`.
- **Orchestrator & Policy Engine:** LLM outputs are treated as untrusted text. Actions matching JSON structures or function calls are passed to `PolicyEngine.evaluate(action, params)`. The orchestrator executes tools strictly if permitted. Hallucinated "result" fields from the LLM are stripped.
- **Memory Subsystem:** SQLite with FTS5 virtual tables for full-text search. Budgeted profile facts are injected into system prompts without extra LLM passes.
- **Audio & Voice Pipeline:** `VoiceSessionManager` serializes `Capture -> STT -> Orchestrator -> TTS -> Playback`.
- **UI & Async Workers:** PySide6 UI runs UI event loops on the main thread and delegates STT/LLM inference to `QThread` workers (`VoiceTurnWorker`, `InferenceWorker`), preventing interface freezes.

---

## 4. Hardware, Models, and Provisioning

| Subsystem | Model / Engine | Quantization / Footprint | Device / Threads | Provisioning State |
| :--- | :--- | :--- | :--- | :--- |
| **LLM Reasoning** | Qwen 2.5/3 1.7B | Q4_K_M GGUF (1.28 GB) | GPU (24 layers) / CPU fallback (4 threads) | Present (`models/Qwen3-1.7B-Q4_K_M.gguf`) |
| **Speech-to-Text** | Whisper-Base | CTranslate2 INT8 (~145 MB) | CPU-only (4 threads) | Present (`models/stt/whisper-base/`) |
| **Text-to-Speech** | Piper (en_US-lessac-medium) | ONNX (~63 MB) | CPU-only | Present (`models/tts/`) |
| **Wake-Word** | Vosk Kaldi (en-us-0.15) | Small Acoustic Model (~40 MB) | CPU-only (energy-gated) | Present (`models/wake_word/`) |
| **Inference Server** | llama.cpp b3000+ | Pre-built binaries (CUDA 12 + AVX2 CPU) | CPU/NVIDIA GPU | Present (`bin/llama.cpp/`) |

---

## 5. Security & Isolation Posture

1. **Network Isolation:** Hardcoded checks in `NetworkIsolationConfig` enforce `allow_external_networking=False` and loopback hosts (`127.0.0.1`, `localhost`, `::1`).
2. **Execution Restrictions:** Dangerous actions (`execute_shell`, `execute_powershell`, `raw_sql`, `drop_table`, `delete_database`) are unconditionally rejected by `PolicyEngine`.
3. **Filesystem Boundaries:** File searches are restricted to authorized directories (`PROJECT_ROOT`, `Desktop`, `Documents`, `Downloads`). Traversal (`..`) and sensitive directories (`Windows`, `Program Files`, `.git`, `.venv`) are blocked.
4. **App Launch Allowlist:** Only approved desktop utilities (`notepad`, `calc`, `mspaint`, `explorer`, `write`, `taskmgr`) can be launched.
5. **Confirmation Gates:** Critical actions (`insert_text`, `delete_task`) require explicit user confirmation.
6. **Privacy Redaction:** Sensitive note content, memory values, and typed text are redacted (`[MEMORY_CONTENT_OMITTED]`) in persistent audit logs.

---

## 6. Existing Test Infrastructure & Testing Gaps

### 6.1 Existing Tests (94 passing)
Existing tests in `tests/` cover individual unit behaviors:
- `test_config.py`, `test_governor.py`: Config defaults, validation, and telemetry.
- `test_policy.py`, `test_audit.py`: Policy whitelists and audit redactions.
- `test_memory.py`: SQLite schema, CRUD, FTS5 recall, prompt injection sanitization.
- `test_tasks.py`: Task CRUD, status updates, due date parsing.
- `test_apps_and_diagnostics.py`, `test_file_search_and_dictation.py`: Safe handlers.
- `test_stt.py`, `test_tts.py`, `test_recorder.py`, `test_wake_word.py`: Mocked audio flows.
- `test_ui.py`: PySide6 offscreen rendering, chat bubbles, RTL detection, workers.
- `test_packaging.py`: Validation of PyInstaller bundle and PE headers.

### 6.2 Testing Gaps Identified
1. **No Unified Quality Lab Harness:** No centralized CLI or runner to execute grouped suites (e.g., `ai`, `voice`, `security`, `performance`, `packaged`, `release`).
2. **Missing Multi-Turn AI Reasoning Evaluation:** Lack of a version-controlled dataset evaluating multi-step tasks, missing parameters, ambiguous instructions, and Persian language reasoning.
3. **No Quantitative Voice Evaluation (WER/CER/Intent):** Audio tests only test mock components or single synthetic utterances; there is no measurement of Word Error Rate (WER), Character Error Rate (CER), or semantic command-intent extraction.
4. **No Wake-Word False Alarm / ROC Evaluation:** No quantified measurement of false activations per hour or missed activations under simulated audio noise.
5. **Absence of Security Regression Suite:** No automated harness continuously testing prompt injection attacks, confirmation token reuse attacks, SQL injection attempts, or symlink traversal.
6. **No Automated Performance & Endurance Instrumentation:** Benchmark script (`src/eval/benchmark.py`) is standalone; no automated regression tracking for TTFT, TPS, CPU/RAM/VRAM baselines, or endurance stress testing.
7. **No Release Gating System:** No policy engine evaluating whether a build is safe and capable of release across security, quality, and performance thresholds.
8. **No Multi-Format Reporting:** No automated HTML, JSON, or JUnit XML report generation with regression comparisons against historical baselines.

---

## 7. Quality Lab Proposed Architecture

The Quality Lab will be implemented in `quality_lab/`:

```
quality_lab/
├── __init__.py
├── cli.py                    # Unified CLI (run, report, compare, list)
├── config.py                 # Quality Lab execution and threshold settings
├── models.py                 # Stable test result schemas, case models, metrics
├── registry.py               # Suite and test case discovery registry
├── orchestrator.py           # Multi-suite runner, capability detection, lifecycle
├── hardware/
│   ├── __init__.py
│   └── detector.py           # Windows hardware, GPU, audio devices, model detection
├── datasets/
│   ├── __init__.py
│   ├── ai_eval_dataset.json  # Comprehensive English & Persian AI evaluation cases
│   └── voice_dataset.json    # Versioned audio fixture metadata and reference transcripts
├── fixtures/
│   ├── __init__.py
│   ├── synthetic_audio.py    # Deterministic WAV/PCM generator for offline voice tests
│   └── mock_environment.py   # Isolated disposable directories, sandbox DBs
├── evaluators/
│   ├── __init__.py
│   ├── deterministic.py      # Schema, tool selection, argument accuracy, policy gates
│   ├── rubrics.py            # Reference checks, semantic rubrics, safety gates
│   └── speech_metrics.py     # WER, CER, Persian text normalizer, intent matchers
├── suites/
│   ├── __init__.py
│   ├── unit_suite.py         # Pure functions, contracts, schemas, error paths
│   ├── integration_suite.py  # Handlers, SQLite persistence, scheduler in temp env
│   ├── ai_eval_suite.py      # AI reasoning, tool selection, injection, Persian/English
│   ├── voice_suite.py        # STT accuracy, WER/CER, semantic command accuracy
│   ├── wake_word_suite.py    # Wake-word activations, silence rejection, debounce
│   ├── tts_suite.py          # Voice availability, RTL/Unicode handling, latency
│   ├── security_suite.py     # Injection, shell/PowerShell block, traversal, confirmation reuse
│   ├── performance_suite.py  # TTFT, TPS, RAM, VRAM, endurance, governor checks
│   ├── gui_suite.py          # Headless PySide6 offscreen UI and worker flows
│   ├── packaged_suite.py     # Packaged exe validation in disposable test environment
│   └── release_gate.py       # Hard blockers, quality gates, pass/fail decisions
├── reporting/
│   ├── __init__.py
│   ├── html_reporter.py      # Rich standalone HTML report with interactive cards
│   ├── json_reporter.py      # Structured JSON report with redacted sensitive content
│   ├── junit_reporter.py     # Standard JUnit XML report for CI/CD integration
│   └── comparator.py         # Regression comparison against baseline runs
└── baselines/
    ├── __init__.py
    └── default_baseline.json # Calibrated thresholds for latency, memory, and accuracy
```

---

## 8. Blockers & Risks

1. **Hardware Dependencies:** Real microphone, speaker, and live GPU inference cannot be mandated for fast local developer workflows. Hardware and heavy model inference tests must be strictly opt-in via `--hardware` and report `INCONCLUSIVE` (rather than failing or silently skipping) if required assets are missing.
2. **Packaged Executable Dependency:** Testing the packaged binary requires `dist/david_assistant/david_assistant.exe` to exist. If absent, the packaged test suite must return an informative `INCONCLUSIVE` result without crashing the overall run.
3. **Zero Internet Requirement:** All tests, evaluation metrics, and audio fixtures must operate 100% offline without remote network queries or automatic downloads.
