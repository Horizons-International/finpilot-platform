[CmdletBinding()]
param(
    [string]$ComposeFile = "docker/docker-compose.yml",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [ValidateRange(15, 120)]
    [int]$TimeoutSeconds = 45,
    [ValidateRange(1, 20)]
    [int]$StableChecks = 5
)

$ErrorActionPreference = "Stop"
$service = "backend-3"
$stopped = $false

function Test-Readiness {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri "$Url/ready" -Method Get -TimeoutSec 3 -UseBasicParsing
        return ($response.StatusCode -eq 200)
    }
    catch {
        return $false
    }
}

Write-Host "Checking initial load-balanced readiness at $BaseUrl/ready ..."
if (-not (Test-Readiness -Url $BaseUrl)) {
    throw "Initial readiness check failed. Start the Compose stack and resolve health errors before testing failover."
}

try {
    Write-Host "Stopping $service to simulate a single application-instance failure..."
    & docker compose -f $ComposeFile stop $service
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose stop $service failed with exit code $LASTEXITCODE."
    }
    $stopped = $true

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $recovered = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Readiness -Url $BaseUrl) {
            $recovered = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $recovered) {
        throw "Load-balanced readiness did not recover within $TimeoutSeconds seconds after stopping $service."
    }

    for ($i = 1; $i -le $StableChecks; $i++) {
        if (-not (Test-Readiness -Url $BaseUrl)) {
            throw "Readiness check $i/$StableChecks failed after failover."
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Host "PASS: HAProxy continued serving readiness requests with $service stopped."
    Write-Host "NOTE: This validates a single application-container failure only; it does not test host, network, load-balancer, or database failure."
}
finally {
    if ($stopped) {
        Write-Host "Restarting $service..."
        & docker compose -f $ComposeFile start $service
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not restart $service automatically. Run: docker compose -f $ComposeFile start $service"
        }
    }
}
