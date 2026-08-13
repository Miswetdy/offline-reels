[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$composeFile = Join-Path $repoRoot 'deploy\docker-compose.stage8-fixture.yml'
$webRoot = Join-Path $repoRoot 'apps\web'

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try { $listener.Start(); return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Wait-FixtureReady {
    param([string]$Origin, [int]$Port)
    for ($attempt = 0; $attempt -lt 100; $attempt += 1) {
        & curl.exe --silent --show-error --fail --insecure --max-time 3 --resolve "localhost:$Port`:127.0.0.1" "$Origin/health/ready" | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }
    throw 'Fixture readiness deadline elapsed.'
}

$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$projectName = "offline-reels-stage8-e2e-$suffix"
$port = Get-FreeLoopbackPort
$origin = "https://localhost:$port"
$saved = @{}
foreach ($name in @('STAGE8_POSTGRES_PASSWORD', 'STAGE8_MINIO_PASSWORD', 'STAGE8_VIDEO_CURSOR_SECRET', 'STAGE8_FIXTURE_PAIRING_SECRET', 'STAGE8_PUBLIC_ORIGIN', 'STAGE8_PORT', 'STAGE8_E2E_ORIGIN', 'STAGE8_E2E_PAIRING_SECRET')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    $env:STAGE8_POSTGRES_PASSWORD = "stage8-postgres-$suffix"
    $env:STAGE8_MINIO_PASSWORD = "stage8-minio-$suffix"
    $env:STAGE8_VIDEO_CURSOR_SECRET = "stage8-cursor-$suffix-0123456789abcdef"
    $env:STAGE8_FIXTURE_PAIRING_SECRET = "stage8-pairing-$suffix-0123456789abcdef"
    $env:STAGE8_PORT = "$port"
    $env:STAGE8_PUBLIC_ORIGIN = $origin
    $env:STAGE8_E2E_ORIGIN = $origin
    $env:STAGE8_E2E_PAIRING_SECRET = $env:STAGE8_FIXTURE_PAIRING_SECRET

    & docker compose --project-name $projectName --file $composeFile up --build --detach
    if ($LASTEXITCODE -ne 0) { throw 'Fixture startup failed.' }
    Wait-FixtureReady -Origin $origin -Port $port
    Push-Location $webRoot
    try {
        & npm exec -- playwright test -c tests/e2e/playwright.stage8.config.ts
        if ($LASTEXITCODE -ne 0) { throw 'Stage 8 Playwright mobile E2E failed.' }
    } finally { Pop-Location }
} finally {
    & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
    $images = @(docker image ls --format '{{.Repository}}:{{.Tag}}' | Where-Object { $_ -like "$projectName-*:*" })
    if ($images.Count -gt 0) { docker image rm $images }
    Remove-Item -LiteralPath (Join-Path $webRoot 'test-results-stage8') -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
}

$containers = docker ps -aq --filter "label=com.docker.compose.project=$projectName"
$volumes = docker volume ls -q --filter "label=com.docker.compose.project=$projectName"
$images = @(docker image ls --format '{{.Repository}}:{{.Tag}}' | Where-Object { $_ -like "$projectName-*:*" })
if ($containers -or $volumes -or $images.Count -gt 0) { throw "Fixture cleanup incomplete: $projectName" }
Write-Output "STAGE8_MOBILE_E2E_CLEANUP_CONFIRMED project=$projectName"
