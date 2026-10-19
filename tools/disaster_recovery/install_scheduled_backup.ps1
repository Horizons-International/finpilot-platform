[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$PythonExe = "",
    [string]$OutputRoot = (Join-Path $env:USERPROFILE "finpilot-backups"),
    [ValidateSet("development", "testing", "production")]
    [string]$Environment = "development",
    [ValidateRange(1, 24)]
    [int]$IntervalHours = 1,
    [switch]$SkipRestoreTestTask
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $RepoRoot).Path
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$ComposeFile = Join-Path $RepoRoot "docker\docker-compose.yml"
if (-not (Test-Path $ComposeFile -PathType Leaf)) {
    throw "Compose file not found: $ComposeFile"
}
if (-not (Test-Path (Join-Path $RepoRoot "scripts\disaster_recovery\automation.py") -PathType Leaf)) {
    throw "DR automation script not found. Merge the ZIP contents into the repository root first."
}

$PythonPrefix = @()
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyCommand) {
        $PythonExe = $pyCommand.Source
        $PythonPrefix = @("-3")
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction Stop
        $PythonExe = $pythonCommand.Source
    }
}
if (-not (Test-Path $PythonExe -PathType Leaf)) {
    throw "Python executable not found: $PythonExe"
}

if ($Environment -eq "production") {
    $persistedRecipient = [Environment]::GetEnvironmentVariable("BACKUP_GPG_RECIPIENT", "User")
    $persistedSigningKey = [Environment]::GetEnvironmentVariable("BACKUP_GPG_SIGNING_KEY", "User")
    if ([string]::IsNullOrWhiteSpace($persistedRecipient) -or [string]::IsNullOrWhiteSpace($persistedSigningKey)) {
        throw "Production task registration requires persistent User environment variables BACKUP_GPG_RECIPIENT and BACKUP_GPG_SIGNING_KEY. Do not set private keys as variables; these are GPG key identifiers. Configure them for this task account, sign out/in, then rerun."
    }
    if (-not (Get-Command gpg.exe -ErrorAction SilentlyContinue)) {
        throw "GPG is required for production encryption/signing but gpg.exe was not found on PATH."
    }
}

function Quote-TaskArgument([string]$Value) {
    if ($Value.Contains('"')) { $Value = $Value.Replace('"', '\"') }
    if ($Value -match '[\s&()]') { return '"' + $Value + '"' }
    return $Value
}

function New-FinPilotAction([string[]]$ModuleArguments) {
    $items = @($PythonPrefix) + @("-m", "scripts.disaster_recovery.automation") + $ModuleArguments
    $argumentLine = ($items | ForEach-Object { Quote-TaskArgument ([string]$_) }) -join ' '
    New-ScheduledTaskAction -Execute $PythonExe -Argument $argumentLine -WorkingDirectory $RepoRoot
}

$backupArguments = @(
    "backup", "--environment", $Environment,
    "--output-root", $OutputRoot,
    "--compose-file", $ComposeFile
)
$backupAction = New-FinPilotAction -ModuleArguments $backupArguments
$firstRun = (Get-Date).AddMinutes(2)
# RepetitionInterval/RepetitionDuration belong to the Once parameter set, not Daily.
# Keep the hourly repetition alive for ten years; rerun this installer before it expires.
$backupTrigger = New-ScheduledTaskTrigger -Once -At $firstRun -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 6)
$backupTask = New-ScheduledTask -Action $backupAction -Trigger $backupTrigger -Principal $principal -Settings $settings -Description "Creates, encrypts when configured, verifies, and records FinPilot backups."
Register-ScheduledTask -TaskName "FinPilot-Automated-Backup" -InputObject $backupTask -Force | Out-Null
Write-Host "Registered FinPilot-Automated-Backup every $IntervalHours hour(s)."

if (-not $SkipRestoreTestTask) {
    $restoreArguments = @(
        "restore-test-latest", "--environment", $Environment,
        "--output-root", $OutputRoot,
        "--compose-file", $ComposeFile
    )
    $restoreAction = New-FinPilotAction -ModuleArguments $restoreArguments
    $restoreTrigger = New-ScheduledTaskTrigger -Daily -At 3:15AM
    $restoreTask = New-ScheduledTask -Action $restoreAction -Trigger $restoreTrigger -Principal $principal -Settings $settings -Description "Verifies and performs a non-destructive daily restore test against the latest FinPilot backup."
    Register-ScheduledTask -TaskName "FinPilot-Daily-Restore-Test" -InputObject $restoreTask -Force | Out-Null
    Write-Host "Registered FinPilot-Daily-Restore-Test daily at 03:15."
}

Write-Host "Backup output root: $OutputRoot"
Write-Host "History command: py -m scripts.disaster_recovery.history --output-root `"$OutputRoot`""
Write-Warning "These tasks use the current interactive Windows account and run only while that account is logged on. For unattended/production operations, use a dedicated service account or an approved server/managed scheduler."
if ($Environment -ne "production") {
    Write-Warning "Environment is '$Environment'; bundles are unencrypted unless BACKUP_GPG_RECIPIENT is configured. Do not use unencrypted bundles for production data."
}
