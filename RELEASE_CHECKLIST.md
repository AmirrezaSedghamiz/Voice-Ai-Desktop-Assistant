# David Assistant: Release Gate & Packaging Verification Checklist

This checklist defines the strict release gate protocol that must be satisfied before distributing a Windows executable release of the David AI Desktop Assistant.

---

## 1. Release Gate Decision Engine

The Quality Lab release gate (`quality_lab.suites.release_gate.ReleaseGateEvaluator`) categorizes test outcomes into **Hard Blockers** (preventing release) and **Warnings** (non-blocking notifications):

### 1.1 Hard Release Blockers (Unconditional Ship-Stoppers)
A release is automatically marked **[FAIL]** if any of the following conditions occur:
1. **Security Suite Failure**: Any failure or error in `security_suite` (zero-tolerance policy on shell leaks, SQL bypasses, or traversal).
2. **Critical Test Failure**: Any test marked with `severity=CRITICAL` fails.
3. **Packaged Binary Failure**: Any test in `packaged_suite` fails (`david_assistant.exe` missing, invalid PE header, missing DLLs, standalone launch crash).
4. **AI Reasoning Accuracy Below Threshold**: AI suite accuracy falls below **90.0%**.
5. **Overall Pass Rate Below Threshold**: Aggregate test pass rate falls below **95.0%**.

### 1.2 Non-Blocking Warnings
- Aggregate pass rate is between 95.0% and 99.0%.
- Performance latency metric exceeds baseline by $> 20\%$.
- Optional physical hardware tests were skipped or inconclusive due to missing microphones or speakers.

---

## 2. Step-by-Step Release Verification Procedure

Follow this checklist sequentially before producing or signing a release:

### Phase 1: Pre-Build Logic & Contract Verification
- [ ] Run the complete baseline test suite:
  ```powershell
  .\.venv\Scripts\pytest.exe -v tests/
  ```
  *Requirement: 94 passed, 0 failed.*

### Phase 2: Windows Distribution Packaging
- [ ] Execute the release packaging script to compile `david_assistant.exe` and bundle native dependencies:
  ```powershell
  .\.venv\Scripts\python.exe scripts/package_release.py
  ```
- [ ] Verify that `dist/david_assistant/` contains:
  - [ ] `david_assistant.exe` (Size: $\sim 13.5\text{ MB}$, valid PE `MZ` header)
  - [ ] `bin/llama.cpp/llama-server.exe`
  - [ ] `assets/david_icon.ico`
  - [ ] `README.txt`
  - [ ] `_internal/` directory containing `PySide6`, `vosk`, `ctranslate2` DLLs

### Phase 3: Quality Lab Release Gate Execution
- [ ] Execute all 10 Quality Lab suites in release mode:
  ```powershell
  .\.venv\Scripts\python.exe -m quality_lab run --suite release
  ```
- [ ] Inspect the execution summary:
  - [ ] `unit` suite: 10/10 PASSED
  - [ ] `integration` suite: 10/10 PASSED
  - [ ] `ai` suite: 20/20 PASSED ($\ge 90.0\%$)
  - [ ] `voice` suite: 10/10 PASSED
  - [ ] `wake_word` suite: 7/7 PASSED
  - [ ] `tts` suite: 7/7 PASSED
  - [ ] `security` suite: 9/9 PASSED (0 policy violations)
  - [ ] `performance` suite: 5/5 PASSED (RAM growth $\le 150\text{ MB}$)
  - [ ] `gui` suite: 6/6 PASSED (clean offscreen Qt rendering)
  - [ ] `packaged` suite: 5/5 PASSED (standalone PE validation)
  - [ ] **RELEASE GATE DECISION: [PASS]**

### Phase 4: Baseline Regression Diff Verification
- [ ] Compare the latest run against the calibrated production baseline:
  ```powershell
  .\.venv\Scripts\python.exe -m quality_lab compare
  ```
  *Requirement: Total Regressions = 0.*

### Phase 5: Standalone Execution Smoke Test
- [ ] Verify standalone execution outside the Python virtual environment:
  ```powershell
  & "dist\david_assistant\david_assistant.exe" --help
  ```
  *Requirement: Process exits with returncode 0; usage help emitted without dependency errors.*

### Phase 6: Report Artifact Archival
- [ ] Ensure execution report artifacts are preserved:
  - HTML Report: `data/quality_lab/reports/run_<timestamp>.html`
  - JSON Report: `data/quality_lab/reports/run_<timestamp>.json`
  - JUnit XML: `data/quality_lab/reports/run_<timestamp>.junit.xml`
- [ ] Open the HTML report in a local browser to verify table rendering and telemetry metadata.
