<#
.SYNOPSIS
    Configures Windows Defender Firewall to block all outbound network traffic
    for the local AI assistant's executables.
.DESCRIPTION
    Creates targeted outbound BLOCK rules for:
    1. bin\llama.cpp\llama-server.exe
    2. .venv\Scripts\python.exe
    Loopback (127.0.0.1) remains functional for internal IPC.
.NOTES
    Requires Administrator privileges.
#>

[CmdletBinding()]
param()

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$llamaServer = Join-Path $projectRoot "bin\llama.cpp\llama-server.exe"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

# Verify actual executable paths exist
if (-not (Test-Path $llamaServer)) {
    Write-Error "Cannot configure firewall: llama-server.exe not found at $llamaServer"
    exit 1
}
if (-not (Test-Path $pythonExe)) {
    Write-Error "Cannot configure firewall: python.exe not found at $pythonExe"
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     Configuring Windows Defender Outbound Block Rules    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target 1 (llama-server): $llamaServer"
Write-Host "Target 2 (python venv) : $pythonExe"

try {
    # 1. Block llama-server outbound
    New-NetFirewallRule -DisplayName "LocalAIAssistant_Block_LlamaServer_Outbound" `
        -Direction Outbound `
        -Program $llamaServer `
        -Action Block `
        -Profile Any `
        -Description "Enforces offline isolation for Local AI Assistant llama-server" `
        -ErrorAction Stop | Out-Null
    Write-Host "[+] Created rule: LocalAIAssistant_Block_LlamaServer_Outbound" -ForegroundColor Green

    # 2. Block project Python venv outbound
    New-NetFirewallRule -DisplayName "LocalAIAssistant_Block_Python_Outbound" `
        -Direction Outbound `
        -Program $pythonExe `
        -Action Block `
        -Profile Any `
        -Description "Enforces offline isolation for Local AI Assistant Python environment" `
        -ErrorAction Stop | Out-Null
    Write-Host "[+] Created rule: LocalAIAssistant_Block_Python_Outbound" -ForegroundColor Green

    Write-Host "`n[SUCCESS] Outbound network isolation configured. Process cannot egress to internet." -ForegroundColor Green
} catch {
    Write-Warning "Failed to create firewall rule. Ensure you are running PowerShell as Administrator."
    Write-Error $_
}
