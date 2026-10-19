[CmdletBinding()]
param(
    [switch]$KeepHistoryAndBackups
)
$ErrorActionPreference = "Stop"
foreach ($taskName in @("FinPilot-Automated-Backup", "FinPilot-Daily-Restore-Test")) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed scheduled task: $taskName"
    }
}
if ($KeepHistoryAndBackups) {
    Write-Host "Existing backup bundles and history were left in place."
} else {
    Write-Host "Backup files and history were NOT deleted. Review and remove them manually only under your retention policy."
}
