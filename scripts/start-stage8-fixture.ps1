[CmdletBinding()]
param(
    [switch]$KeepRunning,
    [string]$PublicOrigin
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$composeFile = Join-Path $repoRoot 'deploy\docker-compose.stage8-fixture.yml'
if (-not (Test-Path -LiteralPath $composeFile)) { throw "Missing fixture compose file: $composeFile" }

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return ([Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function Wait-FixtureReady {
    param([int]$Port)

    for ($attempt = 0; $attempt -lt 60; $attempt += 1) {
        & curl.exe --silent --show-error --fail --insecure --max-time 3 `
            --resolve "localhost:$Port`:127.0.0.1" "https://localhost:$Port/health/ready" | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }
    throw 'Stage 8 fixture did not become ready before the bounded deadline.'
}

$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$projectName = "offline-reels-stage8-$suffix"
$port = Get-FreeLoopbackPort
$fixtureOrigin = "https://localhost:$port"
$funnelHost = 'stage8-funnel.invalid'
if ($PublicOrigin) {
    $publicUri = [Uri]$PublicOrigin
    if ($publicUri.Scheme -ne 'https' -or $publicUri.AbsolutePath -ne '/' -or $publicUri.Query -or $publicUri.Fragment) {
        throw 'PublicOrigin must be an HTTPS origin without a path, query, or fragment.'
    }
    $fixtureOrigin = $publicUri.GetLeftPart([UriPartial]::Authority)
    $funnelHost = $publicUri.Host
}
$saved = @{}
foreach ($name in @(
    'STAGE8_POSTGRES_PASSWORD', 'STAGE8_MINIO_PASSWORD', 'STAGE8_VIDEO_CURSOR_SECRET',
    'STAGE8_FIXTURE_PAIRING_SECRET', 'STAGE8_PUBLIC_ORIGIN', 'STAGE8_PORT', 'STAGE8_CADDY_FUNNEL_HOST'
)) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    $env:STAGE8_POSTGRES_PASSWORD = "stage8-postgres-$suffix"
    $env:STAGE8_MINIO_PASSWORD = "stage8-minio-$suffix"
    $env:STAGE8_VIDEO_CURSOR_SECRET = "stage8-cursor-$suffix-0123456789abcdef"
    $env:STAGE8_FIXTURE_PAIRING_SECRET = "stage8-pairing-$suffix-0123456789abcdef"
    $env:STAGE8_PORT = "$port"
    $env:STAGE8_PUBLIC_ORIGIN = $fixtureOrigin
    $env:STAGE8_CADDY_FUNNEL_HOST = $funnelHost

    & docker compose --project-name $projectName --file $composeFile up --build --detach
    if ($LASTEXITCODE -ne 0) { throw 'Stage 8 fixture startup failed.' }
    Wait-FixtureReady -Port $port
    Write-Output "project=$projectName"
    Write-Output "origin=$env:STAGE8_PUBLIC_ORIGIN"
    Write-Output 'The pairing secret is process-only and intentionally not printed.'
    if (-not $KeepRunning) {
        & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
        if ($LASTEXITCODE -ne 0) { throw 'Stage 8 fixture cleanup failed.' }
    }
} finally {
    foreach ($entry in $saved.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }
}
