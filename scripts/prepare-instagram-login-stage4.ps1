[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = 'offline-reels-instagram-login-stage4'
$compose = Join-Path $PSScriptRoot '..\deploy\docker-compose.instagram-login-stage4.yml'
$envFile = Join-Path $PSScriptRoot '..\deploy\.env.instagram-login-stage4'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'STAGE4_ENV_MISSING' }
foreach ($key in 'LOGIN_POSTGRES_PASSWORD','LOGIN_GATEWAY_SESSION_SECRET','LOGIN_BROWSER_CONTROL_SECRET','LOGIN_VIDEO_CURSOR_SECRET','LOGIN_GATEWAY_ORIGIN','TAILSCALE_AUTHKEY') {
  if (-not (Select-String -LiteralPath $envFile -Pattern "^$key=.+$" -Quiet)) { throw "STAGE4_ENV_INCOMPLETE_$key" }
}
docker compose --project-name $project --env-file $envFile -f $compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'STAGE4_COMPOSE_INVALID' }
docker compose --project-name $project --env-file $envFile -f $compose up --build --detach --wait --wait-timeout 180
if ($LASTEXITCODE -ne 0) { throw 'STAGE4_PREPARE_FAILED' }
