[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:STAGE6_ACCOUNT_ID)) { throw 'STAGE6_ACCOUNT_ID_UNAVAILABLE' }
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    docker compose -f deploy/docker-compose.stage6-smoke.yml up -d --build api
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_FIXTURE_COLLECTOR_BUILD_FAILED' }
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        curl.exe -k --fail --silent https://localhost:18443/health/live | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_FIXTURE_COLLECTOR_API_NOT_READY' }
    $arguments = @(
        'compose', '-f', 'deploy/docker-compose.stage6-smoke.yml', 'exec', '-T', 'api',
        'uv', 'run', '--no-sync', 'python', '-m', 'app.scripts.run_stage6_fixture_collector',
        '--account-id', $env:STAGE6_ACCOUNT_ID, '--delay-seconds', '8'
    )
    $process = Start-Process -FilePath docker -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $env:STAGE6_FIXTURE_COLLECTOR_PID = $process.Id
    Write-Output 'STAGE6_FIXTURE_COLLECTOR_STARTED'
} finally {
    Pop-Location
}
