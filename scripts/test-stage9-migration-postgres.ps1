[CmdletBinding()]
param()

# Isolated migration regression check. It creates one disposable PostgreSQL
# container on a random loopback port and never references Collector smoke,
# fixture E2E, MinIO, Instagram or production Compose resources.
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$apiRoot = Join-Path $repoRoot 'apps\api'
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$containerName = "offline-reels-stage9-migrate-$suffix"
$temporaryBase = Join-Path $repoRoot '.pytest_stage9_migration'
$saved = @{}
foreach ($name in @('DATABASE_URL', 'STAGE9_REAL_POSTGRES', 'VIDEO_CURSOR_SECRET')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try { $listener.Start(); return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

$port = Get-FreeLoopbackPort
try {
    & docker run --detach --rm --name $containerName --publish "127.0.0.1:$port`:5432" --env POSTGRES_DB=stage9_migration --env POSTGRES_USER=stage9_migration --env POSTGRES_PASSWORD="stage9-migration-$suffix" postgres:17.10-alpine3.23 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 migration PostgreSQL startup failed.' }
    for ($attempt = 0; $attempt -lt 60; $attempt += 1) {
        & docker exec $containerName pg_isready --username stage9_migration --dbname stage9_migration | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 500
        if ($attempt -eq 59) { throw 'Stage 9 migration PostgreSQL readiness deadline elapsed.' }
    }
    $env:DATABASE_URL = "postgresql+psycopg://stage9_migration:stage9-migration-$suffix@127.0.0.1:$port/stage9_migration"
    $env:STAGE9_REAL_POSTGRES = '1'
    $env:VIDEO_CURSOR_SECRET = "stage9-migration-cursor-$suffix-0123456789abcdef"
    & uv --directory $apiRoot run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 migration initial Alembic upgrade failed.' }
    & uv --directory $apiRoot run pytest -p no:cacheprovider tests/postgres/test_stage9_migration_postgres.py --basetemp $temporaryBase
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 PostgreSQL migration round-trip failed.' }
    Write-Output "STAGE9_MIGRATION_POSTGRES_PASSED container=$containerName"
} finally {
    if (Test-Path -LiteralPath $temporaryBase) {
        $resolved = (Resolve-Path -LiteralPath $temporaryBase).Path
        if (-not [string]::Equals($resolved, $temporaryBase, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe cleanup target: $resolved" }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    & docker rm --force $containerName 2>$null | Out-Null
    foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
}
