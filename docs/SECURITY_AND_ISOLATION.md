# Security Architecture & Network Isolation

This document defines the security boundaries, threat model, firewall rules, verification procedures, and isolation guarantees for the **Resource-Constrained Local AI Assistant**.

---

## 1. Network Boundary Hierarchy

True offline security requires distinguishing three separate layers of isolation:

```
[ Layer 1: Application AI Inference Boundary ]
  └── Zero remote AI API providers configured.
  └── Inference happens 100% locally on device hardware.

[ Layer 2: Process & Application Network Boundary ]
  └── Operating-system level firewall rules block outbound network egress.
  └── Endpoints are strictly constrained to IPv4 loopback (127.0.0.1).

[ Layer 3: Operating System & Hardware Air-Gap ]
  └── Host computer has all network adapters disconnected or disabled.
  └── Complete physical or virtual air-gap.
```

### Important Engineering Note on Windows Air-Gapping
A regular Windows user-space desktop application **cannot unilaterally guarantee that the entire computer is air-gapped**. While the assistant runtime is blocked from making outbound connections, other applications on the operating system (such as browsers, telemetry daemons, or background services) may still access the internet unless the physical network interface is disconnected.

---

## 2. Threat Model & Security Posture

| Threat Category | Potential Risk | Architectural Mitigation |
| :--- | :--- | :--- |
| **Data Exfiltration** | Prompts, conversation history, or local data sent to remote cloud APIs. | **Local-Only Inference:** Zero remote API providers (OpenAI, Anthropic, cloud gateways). All weights run via `llama-server` on loopback `127.0.0.1`. |
| **Outbound Phone-Home** | Automatic telemetry, update checkers, or library beacons. | **Firewall Outbound Blocking:** Windows Defender Firewall rules block all outbound network traffic for `llama-server.exe` and `.venv\Scripts\python.exe`. |
| **Prompt Injection / Tool Abuse** | Attacker crafts a prompt tricking LLM into running destructive PowerShell/CMD commands. | **Independent Policy Engine:** The LLM does **not** execute actions directly. It proposes actions which must be authorized by an independent, rule-based Policy Engine. Unrestricted shell access is strictly forbidden. |
| **Supply Chain Tampering** | Corrupted or backdoored model weights downloaded during setup. | **Cryptographic Verification:** SHA-256 hashes are calculated and verified against upstream Git LFS manifests before files are extracted or loaded. |
| **Credential Exposure** | API keys or passwords stored insecurely or printed to console logs. | **Audit Log Privacy Redaction:** Regex-based sanitization redacts API tokens, passwords, bearer tokens, and credit card numbers prior to disk persistence. |

---

## 3. Windows Defender Firewall Outbound Blocking

To guarantee process-level outbound isolation, specific outbound block rules are established for the project executables.

### A. Applying Outbound Block Rules
Run from an Administrator PowerShell prompt:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\configure_firewall.ps1
```

This creates two rules in Windows Defender Firewall:
1. `LocalAIAssistant_Block_LlamaServer_Outbound` — Blocks all outbound network communication for:  
   `C:\Users\ACER\Desktop\AI voice assistant\bin\llama.cpp\llama-server.exe`
2. `LocalAIAssistant_Block_Python_Outbound` — Blocks all outbound network communication for:  
   `C:\Users\ACER\Desktop\AI voice assistant\.venv\Scripts\python.exe`

*Note:* Inbound loopback communication between Python and `llama-server` on `127.0.0.1` is preserved, as loopback IPC does not traverse external network adapters.

### B. Verification of Isolation
Run the automated isolation test:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_offline.ps1
```
* **Test 1:** Scans configuration files to ensure zero remote URLs exist.
* **Test 2:** Attempts an outbound HTTPS request from `.venv` Python to `1.1.1.1` (must fail / report `BLOCKED`).
* **Test 3:** Confirms local loopback socket binding succeeds.

### C. Clean Rollback Procedure
To remove all firewall rules created by this project:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\rollback_firewall.ps1
```

---

## 4. Stronger Isolation Options

If complete isolation from a potentially compromised host process is required, consider the following hardening tiers:

1. **Dedicated Offline Windows User Account:**
   * Create a standard (non-administrator) Windows local user with Parental Controls / firewall policies blocking internet access.
2. **Hyper-V / VirtualBox Offline Virtual Machine:**
   * Run the assistant inside a dedicated Windows or Linux VM with the virtual network adapter set to **Disconnected** or **Internal Only**.
   * *Trade-off:* Passing dedicated GPU acceleration (Discrete Device Assignment / DDA) requires GPU partitioning (GPU-PV) on Windows.
3. **Physical Dedicated Air-Gapped Machine:**
   * An isolated laptop or mini-PC with Wi-Fi, Ethernet, and Bluetooth disabled in BIOS.
   * *Trade-off:* Desktop control features (managing host apps, interacting with active windows) will only apply to that dedicated machine.
