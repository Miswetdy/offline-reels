$ErrorActionPreference = 'Stop'
$project = 'offline-reels-collector-smoke'
$compose = 'deploy/docker-compose.collector-smoke.yml'
$envFile = 'deploy/.env.funnel'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'COLLECTOR_SMOKE_ENV_MISSING' }
$containers = @(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Names}}')
$networks = @(docker network ls --filter "label=com.docker.compose.project=$project" --format '{{.Name}}')
$volumes = @(docker volume ls --filter "label=com.docker.compose.project=$project" --format '{{.Name}}')
foreach ($name in @($containers + $networks + $volumes)) {
    if ($name -and -not $name.StartsWith($project, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'COLLECTOR_SMOKE_UNEXPECTED_RESOURCE'
    }
}
Write-Output "Confirmed Collector smoke resources: containers=$($containers.Count) networks=$($networks.Count) volumes=$($volumes.Count)"
docker compose --project-name $project --env-file $envFile -f $compose down --volumes --remove-orphans
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
