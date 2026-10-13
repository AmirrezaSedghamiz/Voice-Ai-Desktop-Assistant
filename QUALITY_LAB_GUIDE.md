# David Assistant: Quality Lab Operational Guide

The **David Quality Lab** (`quality_lab`) is an offline-capable, Windows-native quality testing and evaluation framework designed for the David Desktop AI Assistant. It systematically evaluates language understanding, speech recognition, wake-word activation, tool execution, security policy enforcement, privacy guarantees, performance endurance, GUI responsiveness, and the packaged Windows executable (`david_assistant.exe`).

---

## 1. Design & Architecture Overview

The Quality Lab enforces strict separation of concerns across testing, evaluation, hardware discovery, and reporting:

```
quality_lab/
├── cli.py                  # Command-line interface entry point (run, list, report, compare)
├── config.py               # Quality Lab configuration, paths, and thresholds
├── models.py               # Stable Pydantic result schemas and telemetry models
├── orchestrator.py         # Lifecycle manager, suite executor, and artifact exporter
├── registry.py             # Test suite registration and lazy instantiation
├── hardware/               # Windows host inspection (CPU, RAM, GPU, audio devices, models)
├── evaluators/             # Metric engines (WER/CER, deterministic assertions, rubrics)
├── fixtures/               # Disposable sandboxes, mock LLM clients, synthetic audio waveforms
├── datasets/               # Versioned JSON benchmark sets (AI evaluation & voice test cases)
├── baselines/              # Calibrated release performance and accuracy thresholds
├── suites/                 # 10 dedicated evaluation suites and the release gate evaluator
└── reporting/              # Offline HTML dashboard, JSON summaries, JUnit XML, diff engine
```

### Core Testing Modes

Every test in the Quality Lab explicitly declares its execution mode in its result metadata:

| Test Mode | Description | External Dependencies Required |
| :--- | :--- | :--- |
| `MOCKED` | Fast, deterministic logic testing using mock components or synthetic waveforms | None (CPU only, instantaneous) |
| `INTEGRATION`| Validates interactions between components inside a disposable sandbox | Ephemeral SQLite, temp directories |
| `MODEL` | Performs inference against local models (`Qwen3-1.7B`, `whisper-base`, etc.) | Local weights present; GPU/CPU |
| `HARDWARE` | Interacts with physical host audio devices (Microphone, Speakers) | Physical microphone/sound card |
| `PACKAGED` | Validates compiled PE executable (`david_assistant.exe`) and native DLLs | Built release folder in `dist/` |

---

## 2. CLI Usage & Commands

The Quality Lab CLI can be invoked via `python -m quality_lab`:

### List Available Test Suites
```bash
python -m quality_lab list
```

### Run All Default Fast Suites (Release Mode)
```bash
python -m quality_lab run --suite release
```
*Executes all suites (`unit`, `integration`, `ai`, `voice`, `wake_word`, `tts`, `security`, `performance`, `gui`, `packaged`) without requiring physical audio hardware or downloading external dependencies.*

### Run a Specific Suite
```bash
python -m quality_lab run --suite security
python -m quality_lab run --suite integration
python -m quality_lab run --suite ai
```

### Run with Hardware Devices Enabled (Opt-In)
When running in an interactive hardware environment with physical microphone and speakers:
```bash
python -m quality_lab run --suite voice --hardware
```

### Run with Live Heavy Models (Opt-In)
To evaluate the live local `Qwen3-1.7B-Q4_K_M.gguf` via `llama-server.exe`:
```bash
python -m quality_lab run --suite ai --heavy-model
```

### Filter Tests by ID or Name Pattern
```bash
python -m quality_lab run --suite security --filter SHELL
python -m quality_lab run --suite ai --lang fa
```

### View Latest Report Summary
```bash
python -m quality_lab report --latest
```

### Compare Latest Run Against Baseline
```bash
python -m quality_lab compare
```

---

## 3. Test Suites Catalog

| Suite | Scope & Coverage | Gate Level |
| :--- | :--- | :--- |
| `unit` | Pure functions: emoji stripping, name extraction, fact key normalization, schema defaults. | Critical |
| `integration` | Task CRUD, reminders, FTS5 recall, notes, approved app launching, sandbox search. | High |
| `ai` | Reasoning benchmark: factual EN/FA, tool proposals, parameter checks, injection defense. | Critical |
| `voice` | STT whisper-base: empty audio, ambient silence gating, noise, English & Persian transcripts. | High |
| `wake_word` | Vosk detector: silence, synthetic keyword trigger, non-target phrase rejection, pause/resume. | High |
| `tts` | Piper TTS: markdown stripping, Persian script boundary suppression, RTF latency, unload. | High |
| `security` | Shell blocks, raw SQL rejection, path traversal, confirmation reuse attack, privacy redactions.| Critical |
| `performance` | Governor telemetry overhead, Windows process priority, 50-turn endurance, cancel latency. | Medium |
| `gui` | PySide6 widgets: RTL/LTR HTML rendering, status badges, chat bubbles, cancellation responsiveness.| High |
| `packaged` | PE binary headers (MZ signature), bundled DLLs (`PySide6`, `vosk`), standalone `--help` execution. | Critical |

---

## 4. How to Add New Test Cases

### Adding a New AI Reasoning Case
Edit `quality_lab/datasets/ai_eval_dataset.json` and append an entry:
```json
{
  "id": "AI-TOOL-TASK-LIST-FA-001",
  "category": "tool_execution_fa",
  "language": "fa",
  "input_text": "لیست کارهای من برای امروز چیست؟",
  "expected_behavior": "Proposes list_tasks tool action with status parameter.",
  "requires_tool": true,
  "expected_tool": "list_tasks",
  "expected_params": {},
  "required_concepts": [],
  "forbidden_concepts": ["powershell", "execute_shell"],
  "severity": "high",
  "is_release_gate": true
}
```

### Adding a New Acoustic Voice Case
Edit `quality_lab/datasets/voice_dataset.json`:
```json
{
  "id": "VOICE-CMD-FA-002",
  "language": "fa",
  "category": "command_short",
  "reference_transcript": "وضعیت باتری چقدر است",
  "acoustic_condition": "clean",
  "duration_seconds": 2.1,
  "expected_intent": "get_battery_status",
  "expected_arguments": {},
  "expected_handler": "get_battery_status"
}
```

### Adding a New Integration Test
In `quality_lab/suites/integration_suite.py`:
```python
def _test_new_capability(self) -> TestResult:
    start_t = time.time()
    test_id = "INT-CAP-001"
    name = "New Assistant Capability Verification"
    
    with DisposableSandbox() as sandbox:
        # Perform action inside isolated sandbox
        tools = SafeToolRegistry(
            memory_store=sandbox.memory_store,
            task_manager=sandbox.task_manager,
            policy_engine=sandbox.policy_engine,
        )
        res = tools.some_new_method(...)
        assert res.success is True
        
        return TestResult(
            run_id="",
            test_id=test_id,
            name=name,
            suite="integration",
            status=TestStatus.PASSED,
            mode=TestMode.INTEGRATION,
            duration_seconds=round(time.time() - start_t, 4),
            expected_outcome="Success outcome description",
            observed_outcome="Verified outcome description",
            severity=Severity.HIGH,
        )
```
Then register the function in `self.run()`.

---

## 5. Artifacts and Reporting

When a test run completes, three self-contained artifacts are written to `data/quality_lab/reports/`:
1. `run_<timestamp>.html`: Offline interactive dashboard featuring summary metrics, suite breakdowns, detailed failure diagnostics, and responsive tables.
2. `run_<timestamp>.json`: Machine-readable execution results adhering strictly to the `RunSummary` Pydantic model with sensitive data redaction.
3. `run_<timestamp>.junit.xml`: Standardized JUnit XML report compatible with Windows CI runners and IDE test explorers.
