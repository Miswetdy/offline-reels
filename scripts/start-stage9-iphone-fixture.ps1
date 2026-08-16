[CmdletBinding()]
param(
    [ValidateSet(443, 8443)]
    [int]$FunnelHttpsPort = 443
)

# Starts a disposable Stage 9 fixture for one manual iPhone acceptance.  It
# deliberately does not run Playwright, so the one-time pairing challenge is
# reserved for the phone.  Funnel is configured separately by the operator.
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$composeFile = Join-Path $repoRoot 'deploy\docker-compose.stage9-fixture.yml'
$stateDirectory = Join-Path $repoRoot '.stage9-iphone-fixtures'

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try { $listener.Start(); return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Wait-FixtureReady([string]$Origin, [int]$Port) {
    for ($attempt = 0; $attempt -lt 100; $attempt += 1) {
        & curl.exe --silent --show-error --fail --insecure --max-time 3 --resolve "localhost:$Port`:127.0.0.1" "$Origin/health/ready" | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }
    throw 'Stage 9 iPhone fixture readiness deadline elapsed.'
}

$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$projectName = "offline-reels-stage9-iphone-$suffix"
$statePath = Join-Path $stateDirectory "$projectName.json"
$port = Get-FreeLoopbackPort
$localOrigin = "https://localhost:$port"
$funnelHost = ((& tailscale status --json | ConvertFrom-Json).Self.DNSName.TrimEnd('.'))
if (-not $funnelHost) { throw 'Tailscale DNS name is required for the manual iPhone fixture.' }
$publicPort = if ($FunnelHttpsPort -eq 443) { '' } else { ":$FunnelHttpsPort" }
$publicOrigin = "https://$funnelHost$publicPort"
$pairingSecret = "stage9-iphone-pairing-$suffix-0123456789abcdef"
$secondPairingSecret = "stage9-iphone-pairing-second-$suffix-0123456789abcdef"
$saved = @{}
foreach ($name in @('STAGE9_POSTGRES_PASSWORD', 'STAGE9_MINIO_PASSWORD', 'STAGE9_VIDEO_CURSOR_SECRET', 'STAGE9_FIXTURE_PAIRING_SECRET', 'STAGE9_FIXTURE_SECOND_PAIRING_SECRET', 'STAGE9_PUBLIC_ORIGIN', 'STAGE9_PORT', 'STAGE9_CADDY_FUNNEL_HOST')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$started = $false
try {
    $env:STAGE9_POSTGRES_PASSWORD = "stage9-iphone-postgres-$suffix"
    $env:STAGE9_MINIO_PASSWORD = "stage9-iphone-minio-$suffix"
    $env:STAGE9_VIDEO_CURSOR_SECRET = "stage9-iphone-cursor-$suffix-0123456789abcdef"
    $env:STAGE9_FIXTURE_PAIRING_SECRET = $pairingSecret
    $env:STAGE9_FIXTURE_SECOND_PAIRING_SECRET = $secondPairingSecret
    $env:STAGE9_PORT = "$port"
    $env:STAGE9_CADDY_FUNNEL_HOST = $funnelHost
    # The browser-facing API and FastAPI CSRF origin must be the temporary
    # Funnel hostname. localhost is retained only for loopback readiness.
    $env:STAGE9_PUBLIC_ORIGIN = $publicOrigin
    & docker compose --project-name $projectName --file $composeFile up --build --detach
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 iPhone fixture startup failed.' }
    Wait-FixtureReady -Origin $localOrigin -Port $port
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    @{
        project_name = $projectName
        loopback_port = $port
        local_origin = $localOrigin
        public_origin = $publicOrigin
        funnel_https_port = $FunnelHttpsPort
        compose_file = 'deploy/docker-compose.stage9-fixture.yml'
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
    $started = $true
    Write-Output "STAGE9_IPHONE_FIXTURE_STARTED project=$projectName local_origin=$localOrigin pairing_code=$pairingSecret second_pairing_code=$secondPairingSecret state_path=$statePath"
} finally {
    if (-not $started) {
        & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans 2>$null | Out-Null
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    }
    foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
}
