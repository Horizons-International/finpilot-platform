[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeFile = Join-Path $repoRoot "docker\docker-compose.security-test.yml"
$projectName = "finpilot-security-test"
$compose = @("compose", "--project-name", $projectName, "--file", $composeFile)

Write-Host "=== Docker client/server ===" -ForegroundColor Cyan
docker version
Write-Host "`n=== Security-test containers (including stopped containers) ===" -ForegroundColor Cyan
docker @compose ps -a
Write-Host "`n=== Recent backend and database logs ===" -ForegroundColor Cyan
docker @compose logs --tail 150 security-backend security-postgres
Write-Host "`n=== Local API TCP check ===" -ForegroundColor Cyan
try {
    $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 18080 -WarningAction SilentlyContinue
    if ($tcp.TcpTestSucceeded) {
        Write-Host "TCP port 18080 is accepting connections." -ForegroundColor Green
    } else {
        Write-Host "TCP port 18080 is not accepting connections. The API container may be stopped, unhealthy, or unable to bind the port." -ForegroundColor Red
    }
} catch {
    Write-Host "TCP check failed: $($_.Exception.Message)" -ForegroundColor Red
}
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:18080/health" -TimeoutSec 5
    Write-Host "HTTP health response: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "HTTP health check failed: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host "`nIf the backend is Exited, inspect its logs above. Start again with: .\security-testing\scripts\start-security-test-env.ps1" -ForegroundColor Yellow
