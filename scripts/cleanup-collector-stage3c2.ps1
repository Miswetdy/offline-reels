[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = 'offline-reels-stage3c2-fixture'
$compose = Join-Path $PSScriptRoot '..\deploy\docker-compose.collector-stage3c2-fixture.yml'
$resolved = docker compose --project-name $project -f $compose config --volumes
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the Stage 3C.2 Compose targets.' }
if (($resolved -join "`n") -notmatch 'collector_stage3c2_postgres') {
  throw 'Unexpected Compose volume resolution.'
}

$containers = @(docker ps -aq --filter "label=com.docker.compose.project=$project")
$volumes = @(docker volume ls -q --filter "label=com.docker.compose.project=$project")
Write-Host "Stage 3C.2 containers: $($containers -join ', ')"
Write-Host "Stage 3C.2 volumes: $($volumes -join ', ')"
docker compose --project-name $project -f $compose down --volumes --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'Stage 3C.2 cleanup failed.' }
