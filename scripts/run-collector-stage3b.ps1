param([string]$VerifyResultFile)
$ErrorActionPreference = 'Stop'
$envFile = 'deploy/.env.funnel'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'COLLECTOR_SMOKE_ENV_MISSING' }
$values = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*([^#=\s]+)\s*=\s*(.*?)\s*$') { $values[$matches[1]] = $matches[2].Trim('"') }
}
foreach ($key in 'POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD','MINIO_ACCESS_KEY','MINIO_SECRET_KEY','VIDEO_CURSOR_SECRET') {
    if (-not $values.ContainsKey($key)) { throw 'COLLECTOR_SMOKE_ENV_INCOMPLETE' }
}
$databaseUser = [uri]::EscapeDataString($values['POSTGRES_USER'])
$databasePassword = [uri]::EscapeDataString($values['POSTGRES_PASSWORD'])
$postgresPort = if ($env:COLLECTOR_SMOKE_POSTGRES_PORT) { [int]$env:COLLECTOR_SMOKE_POSTGRES_PORT } else { 55432 }
$minioPort = if ($env:COLLECTOR_SMOKE_MINIO_PORT) { [int]$env:COLLECTOR_SMOKE_MINIO_PORT } else { 59100 }
$env:DATABASE_URL = "postgresql+psycopg://${databaseUser}:${databasePassword}@127.0.0.1:$postgresPort/$($values['POSTGRES_DB'])"
$env:MINIO_ENDPOINT = "http://127.0.0.1:$minioPort"
$env:MINIO_BUCKET = if ($values.ContainsKey('MINIO_BUCKET')) { $values['MINIO_BUCKET'] } else { 'offline-reels' }
$env:MINIO_ACCESS_KEY = $values['MINIO_ACCESS_KEY']
$env:MINIO_SECRET_KEY = $values['MINIO_SECRET_KEY']
$env:VIDEO_CURSOR_SECRET = $values['VIDEO_CURSOR_SECRET']
$env:COLLECTOR_ENABLED = 'true'
$env:COLLECTOR_HEADLESS = 'false'
$env:COLLECTOR_MAXIMUM_TARGET_COUNT = '3'
$env:COLLECTOR_MAXIMUM_RUN_BYTES = '314572800'
$env:COLLECTOR_MAXIMUM_SCROLL_ATTEMPTS = '4'
$env:COLLECTOR_TRANSITION_POLLING_SECONDS = '0.25'
$env:COLLECTOR_TRANSITION_TIMEOUT_SECONDS = '10'
$env:COLLECTOR_COOLDOWN_SECONDS = '0.5'
if (-not $env:COLLECTOR_PROFILE_ROOT) { $env:COLLECTOR_PROFILE_ROOT = Join-Path $env:LOCALAPPDATA 'OfflineReelsCollector\profiles' }
if (-not $env:COLLECTOR_WORKSPACE_ROOT) { $env:COLLECTOR_WORKSPACE_ROOT = Join-Path $env:LOCALAPPDATA 'OfflineReelsCollector\workspace' }
if ($VerifyResultFile) {
    uv --directory apps/api run python -m app.scripts.verify_instagram_collector_run $VerifyResultFile
} else {
    uv --directory apps/api run --extra collector python -m app.scripts.run_instagram_collector_live --target 3
}
exit $LASTEXITCODE
