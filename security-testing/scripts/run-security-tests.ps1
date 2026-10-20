[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:18080"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resultsDir = Join-Path $repoRoot "security-testing\results"
$composeFile = Join-Path $repoRoot "docker\docker-compose.security-test.yml"
$projectName = "finpilot-security-test"

try { $uri = [Uri]$BaseUrl } catch { throw "BaseUrl must be a valid URL. Received: $BaseUrl" }
if ($uri.Scheme -notin @("http", "https")) { throw "BaseUrl must use HTTP or HTTPS." }
if ($uri.Host -notin @("127.0.0.1", "localhost", "::1")) {
    throw "Automated checks are restricted to localhost/loopback. Refusing target '$($uri.Host)'."
}
if ($uri.UserInfo -or $uri.Query -or $uri.Fragment) { throw "BaseUrl must not include credentials, query, or fragment." }

function Show-ComposeDiagnostics {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "Docker CLI was not found; cannot show Compose diagnostics." -ForegroundColor Yellow
        return
    }
    Write-Host "`n--- Security-test Compose status ---" -ForegroundColor Yellow
    & docker compose --project-name $projectName --file $composeFile ps -a
    Write-Host "`n--- Recent security-test container logs ---" -ForegroundColor Yellow
    & docker compose --project-name $projectName --file $composeFile logs --tail 100 security-backend security-postgres
}

New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
$env:SECURITY_TEST_BASE_URL = $BaseUrl.TrimEnd("/")
$junitPath = "security-testing/results/security-tests.xml"

Push-Location $repoRoot
try {
    Write-Host "Checking TCP connectivity to isolated security-test API at $($env:SECURITY_TEST_BASE_URL)..." -ForegroundColor Cyan
    # Use TCP, not GET /health, because this test stack intentionally has a low
    # per-route limit. A health request here would consume the test's budget.
    $port = if ($uri.IsDefaultPort) { if ($uri.Scheme -eq "https") { 443 } else { 80 } } else { $uri.Port }
    $tcpReady = $false
    try {
        $tcp = Test-NetConnection -ComputerName $uri.Host -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
        $tcpReady = [bool]$tcp
    } catch {
        $tcpReady = $false
    }
    if (-not $tcpReady) {
        Write-Host "Cannot reach the security-test API. Pytest would only report connection-refused errors." -ForegroundColor Red
        Show-ComposeDiagnostics
        throw "Security-test API unavailable at $($env:SECURITY_TEST_BASE_URL). Start it with '.\security-testing\scripts\start-security-test-env.ps1'. If it already failed to start, inspect the Compose status and logs printed above."
    }

    Write-Host "Running non-destructive security smoke tests against $($env:SECURITY_TEST_BASE_URL)" -ForegroundColor Cyan
    & uv run --project backend --group dev pytest security-testing/tests -q "--junitxml=$junitPath"
    $testExitCode = $LASTEXITCODE
    if ($testExitCode -ne 0) {
        throw "Security smoke tests failed with exit code $testExitCode. Review $junitPath and fix or triage failures."
    }
    Write-Host "Security smoke tests passed. JUnit report: $junitPath" -ForegroundColor Green
} finally {
    Pop-Location
}
