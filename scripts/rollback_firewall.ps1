<#
.SYNOPSIS
    Removes the Windows Defender Firewall outbound block rules created for the assistant.
.NOTES
    Requires Administrator privileges.
#>

[CmdletBinding()]
param()

Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host "     Rolling Back Windows Defender Firewall Rules         " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Yellow

$rules = @(
    "LocalAIAssistant_Block_LlamaServer_Outbound",
    "LocalAIAssistant_Block_Python_Outbound"
)

foreach ($rule in $rules) {
    try {
        $existing = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
        if ($existing) {
            Remove-NetFirewallRule -DisplayName $rule -ErrorAction Stop
            Write-Host "[+] Removed firewall rule: $rule" -ForegroundColor Green
        } else {
            Write-Host "[-] Rule not found: $rule (already clean)" -ForegroundColor Gray
        }
    } catch {
        Write-Warning "Could not remove rule $rule : $_"
    }
}

Write-Host "`n[SUCCESS] Firewall rollback complete. All project rules removed." -ForegroundColor Green
