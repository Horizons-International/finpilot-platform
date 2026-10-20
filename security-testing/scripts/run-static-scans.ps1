$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resultsDir = Join-Path $repoRoot "security-testing\results"
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null

$banditReport = "security-testing/results/bandit.json"
$auditReport = "security-testing/results/pip-audit.json"
$banditExit = 0
$auditExit = 0

Push-Location $repoRoot
try {
    Write-Host "Running Bandit against backend/app..." -ForegroundColor Cyan
    & uvx bandit -r backend/app --format json --output $banditReport
    $banditExit = $LASTEXITCODE
    if (Test-Path $banditReport) { Write-Host "Bandit report: $banditReport" }

    Write-Host "Running pip-audit against the resolved backend environment..." -ForegroundColor Cyan
    & uv run --project backend --group dev --with pip-audit pip-audit --format json --output $auditReport
    $auditExit = $LASTEXITCODE
    if (Test-Path $auditReport) { Write-Host "Dependency audit report: $auditReport" }
} finally {
    Pop-Location
}

if ($banditExit -ne 0 -or $auditExit -ne 0) {
    Write-Warning "One or more scanner commands returned a non-zero exit code. This may indicate findings or a tool/network error; inspect the console output and JSON reports."
    exit 1
}
Write-Host "Both scanner commands completed without reporting a failure. Review the reports anyway; an empty scan result is not proof that the platform is secure." -ForegroundColor Green
