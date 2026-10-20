$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeFile = Join-Path $repoRoot "docker\docker-compose.security-test.yml"
$projectName = "finpilot-security-test"
$composePrefix = @("compose", "--project-name", $projectName, "--file", $composeFile)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found on PATH. Install/start Docker Desktop, then retry."
}

function Show-ComposeDiagnostics {
    Write-Host "`n--- Security-test Compose status ---" -ForegroundColor Yellow
    & docker @composePrefix ps -a
    Write-Host "`n--- Recent security-test container logs ---" -ForegroundColor Yellow
    & docker @composePrefix logs --tail 120 security-backend security-postgres
}

Push-Location $repoRoot
try {
    Write-Host "Starting isolated FinPilot security-test stack..." -ForegroundColor Cyan
    & docker @composePrefix up --detach --build
    if ($LASTEXITCODE -ne 0) {
        Show-ComposeDiagnostics
        throw "docker compose up failed with exit code $LASTEXITCODE. Review the status/logs above."
    }

    Write-Host "Applying migrations to the dedicated security-test database..." -ForegroundColor Cyan
    & docker @composePrefix exec --no-TTY security-backend uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Show-ComposeDiagnostics
        throw "Alembic migration failed. Review the status/logs above before running pytest."
    }

    $healthUri = "http://127.0.0.1:18080/health"
    $deadline = (Get-Date).AddSeconds(90)
    do {
        try {
            $response = Invoke-WebRequest -Uri $healthUri -Method Get -TimeoutSec 4
            if ($response.StatusCode -eq 200) {
                Write-Host "Security-test API is responding at http://127.0.0.1:18080" -ForegroundColor Green
                Write-Host "Database is private to the Compose network (security-postgres:5432)."
                Write-Host "Next: .\security-testing\scripts\run-security-tests.ps1"
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    Show-ComposeDiagnostics
    throw "The security-test API did not return HTTP 200 from /health within 90 seconds. Do not run pytest yet; resolve the container startup error shown above."
} finally {
    Pop-Location
}
