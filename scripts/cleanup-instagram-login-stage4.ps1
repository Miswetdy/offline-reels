[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = 'offline-reels-instagram-login-stage4'
$compose = Join-Path $PSScriptRoot '..\deploy\docker-compose.instagram-login-stage4.yml'
$envFile = Join-Path $PSScriptRoot '..\deploy\.env.instagram-login-stage4'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'STAGE4_ENV_MISSING' }
$volumes = @(docker volume ls -q --filter "label=com.docker.compose.project=$project")
foreach ($volume in $volumes) {
  if ($volume -notmatch 'stage4_(login_(postgres|profile)|tailscale_state)$') { throw "Unexpected Stage 4 volume: $volume" }
}
docker compose --project-name $project --env-file $envFile -f $compose down --volumes --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'STAGE4_CLEANUP_FAILED' }
