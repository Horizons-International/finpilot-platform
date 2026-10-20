[CmdletBinding()]
param(
    [ValidateRange(1, 86400)]
    [int]$DurationSeconds = 600,
    [ValidateRange(1, 300)]
    [int]$IntervalSeconds = 5,
    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI is required to sample container resource usage.'
}
$repoRoot = (Get-Location).Path
if (-not $OutputPath) {
    $resultsDir = Join-Path $repoRoot 'performance/results'
    New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
    $OutputPath = Join-Path $resultsDir ('docker-stats-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.csv')
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $repoRoot $OutputPath
}
$outputDir = Split-Path -Parent $OutputPath
if ($outputDir) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }

$header = 'timestamp_utc,container,cpu_percent,memory_usage,memory_percent,network_io,block_io,pids'
if (-not (Test-Path $OutputPath)) { Set-Content -Path $OutputPath -Value $header -Encoding utf8 }
$deadline = (Get-Date).AddSeconds($DurationSeconds)
$format = '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}'
Write-Host "Sampling Docker resource usage every $IntervalSeconds second(s) for $DurationSeconds second(s)."
Write-Host "CSV: $OutputPath"
while ((Get-Date) -lt $deadline) {
    $now = (Get-Date).ToUniversalTime().ToString('o')
    $rows = & docker stats --no-stream --format $format
    if ($LASTEXITCODE -ne 0) { throw 'docker stats failed. Is Docker Desktop running?' }
    foreach ($line in $rows) {
        if (-not $line) { continue }
        $parts = $line -split ',', 7
        if ($parts.Count -ne 7) {
            Write-Warning "Skipping unrecognized docker stats row: $line"
            continue
        }
        $row = [pscustomobject]@{
            timestamp_utc = $now
            container = $parts[0]
            cpu_percent = $parts[1]
            memory_usage = $parts[2]
            memory_percent = $parts[3]
            network_io = $parts[4]
            block_io = $parts[5]
            pids = $parts[6]
        }
        $row | ConvertTo-Csv -NoTypeInformation | Select-Object -Skip 1 | Add-Content -Path $OutputPath -Encoding utf8
    }
    Start-Sleep -Seconds $IntervalSeconds
}
Write-Host "Docker stats capture complete: $OutputPath"
