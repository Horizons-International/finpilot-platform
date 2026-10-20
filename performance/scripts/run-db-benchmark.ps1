[CmdletBinding()]
param(
    [int]$Iterations = 5,
    [int]$StatementTimeoutMs = 15000
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Get-Location).Path
$scriptPath = Join-Path $repoRoot 'performance/scripts/benchmark_database.py'
if (-not (Test-Path $scriptPath)) {
    throw 'Run this script from the FinPilot repository root after extracting the bundle.'
}
Write-Warning 'Run only against a dedicated test/staging database with a least-privileged account. This script issues read-only aggregate queries.'
& uv run --project backend python $scriptPath --confirm-test-environment --iterations $Iterations --statement-timeout-ms $StatementTimeoutMs
if ($LASTEXITCODE -ne 0) {
    throw "Database benchmark failed with exit code $LASTEXITCODE."
}
