[CmdletBinding()]
param()

# Runs real PostgreSQL control-plane races in one disposable container.  This
# never uses Compose, Collector smoke, MinIO, Instagram, or production state.
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$apiRoot = Join-Path $repoRoot 'apps\api'
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$containerName = "offline-reels-stage9-control-$suffix"
$temporaryBase = Join-Path $repoRoot '.pytest_stage9_control_plane'
$saved = @{}
foreach ($name in @('DATABASE_URL', 'STAGE6_REAL_POSTGRES', 'VIDEO_CURSOR_SECRET', 'FRONTEND_ORIGIN', 'MANAGEMENT_ORIGIN')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try { $listener.Start(); return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

$port = Get-FreeLoopbackPort
try {
    & docker run --detach --rm --name $containerName --publish "127.0.0.1:$port`:5432" --env POSTGRES_DB=stage9_control --env POSTGRES_USER=stage9_control --env POSTGRES_PASSWORD="stage9-control-$suffix" postgres:17.10-alpine3.23 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 control-plane PostgreSQL startup failed.' }
    for ($attempt = 0; $attempt -lt 60; $attempt += 1) {
        & docker exec $containerName pg_isready --username stage9_control --dbname stage9_control | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 500
        if ($attempt -eq 59) { throw 'Stage 9 control-plane PostgreSQL readiness deadline elapsed.' }
    }
    $env:DATABASE_URL = "postgresql+psycopg://stage9_control:stage9-control-$suffix@127.0.0.1:$port/stage9_control"
    # Existing real-PG control-plane tests intentionally require this explicit opt-in.
    $env:STAGE6_REAL_POSTGRES = '1'
    $env:VIDEO_CURSOR_SECRET = "stage9-control-cursor-$suffix-0123456789abcdef"
    # Must match the explicit HTTPS TestClient origin in the real-race suite.
    $env:FRONTEND_ORIGIN = 'https://localhost:18443'
    $env:MANAGEMENT_ORIGIN = 'https://localhost:18443'
    & uv --directory $apiRoot run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 control-plane Alembic upgrade failed.' }
    & uv --directory $apiRoot run pytest -p no:cacheprovider tests/postgres/test_management_control_plane_postgres.py --basetemp $temporaryBase
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 PostgreSQL control-plane test suite failed.' }
    Write-Output "STAGE9_CONTROL_PLANE_POSTGRES_PASSED container=$containerName"
} finally {
    if (Test-Path -LiteralPath $temporaryBase) {
        $resolved = (Resolve-Path -LiteralPath $temporaryBase).Path
        if (-not [string]::Equals($resolved, $temporaryBase, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe cleanup target: $resolved" }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    & docker rm --force $containerName 2>$null | Out-Null
    foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
}
