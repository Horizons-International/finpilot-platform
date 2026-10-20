[CmdletBinding()]
param(
    [ValidateSet('smoke', 'baseline', 'load', 'stress')]
    [string]$Profile = 'smoke',
    [string]$HostUrl = $(if ($env:PERF_BASE_URL) { $env:PERF_BASE_URL } else { 'http://127.0.0.1:8000' }),
    [int]$Users = 0,
    [int]$SpawnRate = 0,
    [string]$RunTime = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Get-Location).Path
$locustfile = Join-Path $repoRoot 'performance/locustfile.py'
if (-not (Test-Path $locustfile)) {
    throw 'Run this script from the FinPilot repository root after extracting the bundle.'
}
if (-not (Get-Command locust -ErrorAction SilentlyContinue)) {
    throw 'Locust is not installed. Run: py -m pip install -r performance/requirements.txt'
}
if (-not $env:PERF_ACCESS_TOKEN -and (-not $env:PERF_EMAIL -or -not $env:PERF_PASSWORD)) {
    throw 'Set PERF_EMAIL and PERF_PASSWORD (recommended) or PERF_ACCESS_TOKEN before starting.'
}

switch ($Profile) {
    'smoke'    { if ($Users -le 0) { $Users = 1 };  if ($SpawnRate -le 0) { $SpawnRate = 1 }; if (-not $RunTime) { $RunTime = '1m' } }
    'baseline' { if ($Users -le 0) { $Users = 5 };  if ($SpawnRate -le 0) { $SpawnRate = 1 }; if (-not $RunTime) { $RunTime = '5m' } }
    'load'     { if ($Users -le 0) { $Users = 25 }; if ($SpawnRate -le 0) { $SpawnRate = 5 }; if (-not $RunTime) { $RunTime = '10m' } }
    'stress'   { if ($Users -le 0) { $Users = 50 }; if ($SpawnRate -le 0) { $SpawnRate = 5 }; if (-not $RunTime) { $RunTime = '10m' } }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$resultsDir = Join-Path $repoRoot 'performance/results'
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null
$prefix = Join-Path $resultsDir "$Profile-$stamp"
$html = "$prefix.html"

Write-Host "Profile: $Profile | Host: $HostUrl | Users: $Users | Spawn rate: $SpawnRate/s | Runtime: $RunTime"
Write-Host "Results will be written under: $resultsDir"
if ($Profile -in @('load', 'stress')) {
    Write-Warning 'Start with a test/staging environment. Write-producing tasks are opt-in, but read/AI workloads still consume resources.'
}

$argsList = @(
    '-f', $locustfile,
    '--headless',
    '--host', $HostUrl,
    '--users', "$Users",
    '--spawn-rate', "$SpawnRate",
    '--run-time', $RunTime,
    '--stop-timeout', '30',
    '--csv', $prefix,
    '--html', $html,
    '--csv-full-history'
)
& locust @argsList
$exitCode = $LASTEXITCODE
$failuresCsv = "${prefix}_failures.csv"
$failureRows = @()
if (Test-Path $failuresCsv) {
    $failureRows = @(Import-Csv -Path $failuresCsv)
}

if ($exitCode -ne 0) {
    throw "Locust exited with code $exitCode. Review the output and generated result files."
}
if ($failureRows.Count -gt 0) {
    throw "Locust recorded $($failureRows.Count) failure entr$(if ($failureRows.Count -eq 1) { 'y' } else { 'ies' }). Review $failuresCsv before accepting this run."
}
Write-Host "HTML report: $html"
Write-Host "CSV prefix: $prefix"
Write-Host 'No request failures were recorded.'
