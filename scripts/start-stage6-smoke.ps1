[CmdletBinding()]
param([int]$TimeoutSeconds = 180)

$ErrorActionPreference = 'Stop'

function New-ProcessSecret {
    $bytes = New-Object byte[] 36
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    $env:STAGE6_POSTGRES_PASSWORD = New-ProcessSecret
    $env:STAGE6_VIDEO_CURSOR_SECRET = New-ProcessSecret
    docker compose -f deploy/docker-compose.stage6-smoke.yml up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_SMOKE_START_FAILED' }
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        curl.exe -k --fail --silent https://localhost:18443/health/live | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Output 'STAGE6_SMOKE_READY'
            exit 0
        }
        Start-Sleep -Seconds 2
    }
    throw 'STAGE6_SMOKE_API_NOT_READY'
} finally {
    Pop-Location
}
