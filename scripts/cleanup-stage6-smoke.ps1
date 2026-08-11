[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    if (-not [string]::IsNullOrWhiteSpace($env:STAGE6_COOKIE_JAR)) {
        Remove-Item -LiteralPath $env:STAGE6_COOKIE_JAR -Force -ErrorAction SilentlyContinue
    }
    docker compose -f deploy/docker-compose.stage6-smoke.yml down --volumes --remove-orphans
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_SMOKE_CLEANUP_FAILED' }
    Write-Output 'STAGE6_SMOKE_CLEANED'
} finally {
    foreach ($name in @(
        'STAGE6_PAIRING_SECRET', 'STAGE6_CSRF_TOKEN', 'STAGE6_COOKIE_JAR',
        'STAGE6_LOGIN_ID', 'STAGE6_LOGIN_CREATE_KEY', 'STAGE6_RUN_ID',
        'STAGE6_COLLECTION_CREATE_KEY', 'STAGE6_ACCOUNT_ID', 'STAGE6_FIXTURE_COLLECTOR_PID'
    )) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    Pop-Location
}
