[CmdletBinding()]
param(
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeFile = Join-Path $repoRoot "docker\docker-compose.security-test.yml"
$projectName = "finpilot-security-test"
$composeArgs = @("compose", "--project-name", $projectName, "--file", $composeFile, "down")
if ($RemoveData) {
    $composeArgs += "--volumes"
    Write-Warning "This deletes the dedicated security-test database volume for project '$projectName'."
}

& docker @composeArgs
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed with exit code $LASTEXITCODE" }
if ($RemoveData) {
    Write-Host "Security-test containers and their dedicated data volume have been removed." -ForegroundColor Yellow
} else {
    Write-Host "Security-test containers stopped. The dedicated database volume was retained."
}
