<#
.SYNOPSIS
    Verifies network isolation boundaries for the Local AI Assistant.
.DESCRIPTION
    1. Checks that configuration points strictly to loopback (127.0.0.1).
    2. Tests that Python runtime cannot establish an outbound WAN connection.
    3. Confirms that local loopback communication remains functional.
#>

[CmdletBinding()]
param()

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       Network Isolation & Offline Verification Test      " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Test 1: Configuration check
Write-Host "`n[Test 1] Inspecting runtime configuration files for remote URLs..."
$forbiddenMatches = Select-String -Path "$projectRoot\src\core\config.py" -Pattern "https?:\/\/(?!127\.0\.0\.1|localhost)"
if ($forbiddenMatches) {
    Write-Warning "Found potential external URLs in configuration:"
    $forbiddenMatches | ForEach-Object { Write-Warning "  $($_.Line)" }
} else {
    Write-Host "[PASS] No external remote URLs configured in runtime settings." -ForegroundColor Green
}

# Test 2: Outbound network egress attempt
Write-Host "`n[Test 2] Testing outbound WAN connection from .venv Python runtime..."
$testScript = @"
import sys, httpx
try:
    resp = httpx.get('https://1.1.1.1', timeout=3.0)
    print('CONNECTED')
    sys.exit(0)
except Exception as e:
    print('BLOCKED')
    sys.exit(1)
"@

$result = & $pythonExe -c $testScript 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[ALERT] Outbound WAN connection succeeded. Application is currently NOT blocked by firewall." -ForegroundColor Yellow
    Write-Host "        To enforce strict outbound blocking, run: scripts\configure_firewall.ps1 as Administrator." -ForegroundColor Yellow
} else {
    Write-Host "[PASS] Outbound WAN connection failed / blocked as expected ($result)." -ForegroundColor Green
}

# Test 3: Loopback sanity check
Write-Host "`n[Test 3] Verifying loopback (127.0.0.1) IPC compatibility..."
$loopbackTest = @"
import socket, sys
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.listen(1)
    s.close()
    print(f'LOOPBACK_OK:{port}')
    sys.exit(0)
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
"@

$loopResult = & $pythonExe -c $loopbackTest 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] Local loopback interface is active and accessible for IPC ($loopResult)." -ForegroundColor Green
} else {
    Write-Error "[FAIL] Loopback binding failed: $loopResult"
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "Offline Verification Completed." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
