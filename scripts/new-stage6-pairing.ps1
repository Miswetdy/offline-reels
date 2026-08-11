[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$accountId = [guid]::NewGuid().Guid
Push-Location $repoRoot
try {
    $lines = @(docker compose -f deploy/docker-compose.stage6-smoke.yml exec -T api `
        uv run --no-sync python -m app.scripts.management create-pairing --account-id $accountId)
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_PAIRING_CREATE_FAILED' }
    $secretLine = $lines | Where-Object { $_ -like 'PAIRING_SECRET=*' } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($secretLine)) { throw 'STAGE6_PAIRING_SECRET_UNAVAILABLE' }
    $env:STAGE6_PAIRING_SECRET = $secretLine.Substring('PAIRING_SECRET='.Length)
    $env:STAGE6_ACCOUNT_ID = $accountId
    Write-Output "STAGE6_PAIRING_READY account_id=$accountId"
} finally {
    Pop-Location
}
