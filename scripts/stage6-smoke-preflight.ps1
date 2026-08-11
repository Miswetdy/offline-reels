[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    $previousPassword = $env:STAGE6_POSTGRES_PASSWORD
    $previousCursor = $env:STAGE6_VIDEO_CURSOR_SECRET
    $env:STAGE6_POSTGRES_PASSWORD = 'preflight-placeholder-not-a-secret'
    $env:STAGE6_VIDEO_CURSOR_SECRET = 'preflight-placeholder-video-cursor-secret-32'
    docker compose -f deploy/docker-compose.stage6-smoke.yml config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_SMOKE_COMPOSE_INVALID' }
    $busy = Get-NetTCPConnection -LocalPort 18443 -State Listen -ErrorAction SilentlyContinue
    if ($busy) { throw 'STAGE6_SMOKE_PORT_IN_USE' }
    Write-Output 'STAGE6_SMOKE_PREFLIGHT_OK'
} finally {
    $env:STAGE6_POSTGRES_PASSWORD = $previousPassword
    $env:STAGE6_VIDEO_CURSOR_SECRET = $previousCursor
    Pop-Location
}
