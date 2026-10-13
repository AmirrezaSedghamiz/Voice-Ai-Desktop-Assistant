# David Assistant: Performance Baselines & Windows Hardware Telemetry

This document outlines the performance benchmarks, endurance testing methodologies, hardware capabilities, and regression tolerances established for the David Desktop AI Assistant.

---

## 1. Reference Windows Host Hardware Profile

The Quality Lab automatically audits and logs host hardware telemetry at the beginning of each run via `quality_lab.hardware.detector.WindowsHardwareDetector`:

| Telemetry Dimension | Host System Specification | Operational Impact |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 AMD64 (Build 10.0.26200) | Native Windows APIs, WinMM audio, UTF-8 console |
| **Processor (CPU)** | 14 Physical Cores / 20 Logical vCPUs | Multi-threaded inference & Vosk audio streaming |
| **System Memory (RAM)**| 23.71 GB Total / 4.8 GB Free | Sufficient headroom for LLM + Whisper + Piper |
| **Dedicated GPU** | NVIDIA GeForce RTX 3050 Ti Laptop GPU | CUDA acceleration for GGUF model layers |
| **VRAM Capacity** | 4096 MB GDDR6 | Permits up to 24-28 GPU layers for Qwen3-1.7B |
| **Display Platform** | Windows Native DWM / Qt Offscreen | Headless offscreen support for automated suites |
| **Audio Subsystem** | 12 Input Devices / 12 Output Devices | Real-time 16kHz audio capture and WASAPI playback |

---

## 2. Resource Governor Telemetry & Overhead

The `ResourceGovernor` (`src.core.governor.ResourceGovernor`) monitors CPU, RAM, and GPU load dynamically to throttle background services and protect host responsiveness:

### 2.1 Telemetry Collection Overhead
- Collecting system telemetry must not introduce perceivable latency into user interaction turns.
- **Benchmark Target**: $\text{Overhead} < 5.0\text{ ms}$
- **Observed Production**: $\mathbf{0.08\text{ ms}}$ per snapshot (`PERF-GOV-OVERHEAD-001`).

### 2.2 Windows Process Priority Management
- To guarantee that background inference never degrades Windows desktop responsiveness or causes audio playback stutter, David sets its Windows process priority class to `BELOW_NORMAL_PRIORITY_CLASS`:
```python
p = psutil.Process()
p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
```
- **Verified in Test**: `PERF-WIN-PRIORITY-002` asserts that the active process operates under below-normal scheduling.

---

## 3. Endurance & Memory Leak Benchmark

Continuous desktop applications must maintain stable memory footprints without gradual leaks across extended conversational sessions:

### 3.1 50-Turn Continuous Endurance Loop
The Quality Lab executes a 50-turn synthetic workload (`PERF-ENDURANCE-50TURNS-003`) consisting of sequential user inputs, task queries, memory lookups, and simulated responses.

### 3.2 Memory Stability Metric
$$\Delta\text{RAM} = \text{RAM}_{\text{end}} - \text{RAM}_{\text{start}}$$
- **Acceptance Threshold**: $\Delta\text{RAM} \le 150.0\text{ MB}$ across 50 turns.
- **Observed Production**: $\Delta\text{RAM} \approx \mathbf{0.0\text{ MB}}$ (ephemeral object lifecycles collected cleanly by Python GC).

---

## 4. Latency Budgets & Cancellation Responsiveness

| Action / Operation | Maximum Allowed Latency | Observed Baseline | Test ID |
| :--- | :--- | :--- | :--- |
| User Cancellation Dispatch | $< 100.0\text{ ms}$ | $\mathbf{10.41\text{ ms}}$ | `PERF-CANCEL-LATENCY-005` |
| Task Database Insertion | $< 50.0\text{ ms}$ | $\mathbf{4.2\text{ ms}}$ | `INT-TASK-CRUD-001` |
| FTS5 Full-Text Recall | $< 30.0\text{ ms}$ | $\mathbf{2.8\text{ ms}}$ | `INT-MEMORY-FTS5-004` |
| TTS Synthesis (Short Prompt) | $< 300.0\text{ ms}$ | $\mathbf{158.9\text{ ms}}$ | `TTS-ONNX-SYNTH-004` |
| UI Offscreen Render Turn | $< 50.0\text{ ms}$ | $\mathbf{13.7\text{ ms}}$ | `GUI-WINDOW-CANCEL-005` |

---

## 5. Calibrated Baseline & Regression Detection

The Quality Lab maintains a versioned reference baseline in `quality_lab/baselines/default_baseline.json`:

```json
{
  "version": "1.0.0",
  "min_overall_pass_rate": 0.95,
  "min_ai_accuracy": 0.90,
  "max_telemetry_overhead_ms": 5.0,
  "max_cancel_latency_ms": 100.0,
  "max_tts_rtf": 0.50,
  "max_memory_growth_mb": 150.0
}
```

### Regression Diff Engine (`python -m quality_lab compare`)
When comparing a test run against the baseline:
1. **Pass Rate Regressions**: Any suite whose pass rate falls below the baseline tolerance is flagged as a regression.
2. **Timing Regressions**: Any operation that exceeds its latency threshold by $> 25\%$ triggers a performance warning.
3. **Security Regressions**: Any failure in the `security` suite produces a hard release blocker unconditionally.
