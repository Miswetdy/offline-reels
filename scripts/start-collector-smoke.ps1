param([int]$TimeoutSeconds = 180)
$ErrorActionPreference = 'Stop'
$project = 'offline-reels-collector-smoke'
$compose = 'deploy/docker-compose.collector-smoke.yml'
$postgresPort = if ($env:COLLECTOR_SMOKE_POSTGRES_PORT) { [int]$env:COLLECTOR_SMOKE_POSTGRES_PORT } else { 55432 }
$minioPort = if ($env:COLLECTOR_SMOKE_MINIO_PORT) { [int]$env:COLLECTOR_SMOKE_MINIO_PORT } else { 59100 }

function Get-SmokeContainerId([string]$service) {
    $id = docker compose --project-name $project --env-file deploy/.env.funnel -f $compose ps -a -q $service
    if ($LASTEXITCODE -ne 0) { throw 'COLLECTOR_SMOKE_STATUS_FAILED' }
    return ($id | Select-Object -First 1)
}

function Test-OwnPort([int]$port) {
    if ($port -lt 1 -or $port -gt 65535) { throw 'COLLECTOR_SMOKE_PORT_EXCLUDED' }
    if ($port -in @(5432, 9000, 9001)) { throw 'COLLECTOR_SMOKE_PORT_EXCLUDED' }
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $listeners) { return $false }
    $containerIds = docker ps --filter "label=com.docker.compose.project=$project" --format '{{.ID}}'
    if ($LASTEXITCODE -ne 0) { throw 'COLLECTOR_SMOKE_STATUS_FAILED' }
    foreach ($id in $containerIds) {
        $bindings = docker port $id 2>$null
        if ($bindings -match "127\.0\.0\.1:$port$") { return $true }
    }
    throw 'COLLECTOR_SMOKE_PORT_IN_USE'
}

function Show-SafeStatus {
    foreach ($service in 'postgres','minio','minio-bootstrap','migrate') {
        $id = Get-SmokeContainerId $service
        if ($id) {
            docker inspect --format '{{.Name}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} exit={{.State.ExitCode}}' $id
        }
    }
    $safeLogs = docker compose --project-name $project --env-file deploy/.env.funnel -f $compose logs --no-color --tail 20 postgres minio minio-bootstrap migrate 2>&1
    foreach ($line in $safeLogs) {
        $redacted = $line -replace 'https?://\S+', '[redacted-url]'
        $redacted = $redacted -replace '(?i)(password|secret|token|access[_-]?key)\s*[=:]\s*\S+', '$1=[redacted]'
        Write-Output $redacted
    }
}

foreach ($port in $postgresPort, $minioPort) { [void](Test-OwnPort $port) }
Write-Output "Collector smoke ports: PostgreSQL=$postgresPort MinIO=$minioPort"
docker compose --project-name $project --env-file deploy/.env.funnel -f $compose up -d postgres minio minio-bootstrap migrate
if ($LASTEXITCODE -ne 0) { Show-SafeStatus; exit 1 }

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$ready = $false
while ([DateTime]::UtcNow -lt $deadline) {
    $postgresId = Get-SmokeContainerId 'postgres'
    $minioId = Get-SmokeContainerId 'minio'
    $bootstrapId = Get-SmokeContainerId 'minio-bootstrap'
    $migrateId = Get-SmokeContainerId 'migrate'
    if ($postgresId -and $minioId -and $bootstrapId -and $migrateId) {
        $postgresHealth = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' $postgresId
        $minioHealth = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' $minioId
        $bootstrapState = docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' $bootstrapId
        $migrateState = docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' $migrateId
        if ($postgresHealth -eq 'healthy' -and $minioHealth -eq 'healthy' -and $bootstrapState -eq 'exited:0' -and $migrateState -eq 'exited:0') {
            $ready = $true
            break
        }
        if ($bootstrapState -match '^exited:(?!0$)' -or $migrateState -match '^exited:(?!0$)') { break }
    }
    Start-Sleep -Seconds 2
}
if (-not $ready) { Show-SafeStatus; exit 1 }

docker compose --project-name $project --env-file deploy/.env.funnel -f $compose run --rm --no-deps migrate uv run --no-sync alembic current --check-heads
if ($LASTEXITCODE -ne 0) { Show-SafeStatus; exit 1 }
Write-Output 'COLLECTOR_SMOKE_READY'
