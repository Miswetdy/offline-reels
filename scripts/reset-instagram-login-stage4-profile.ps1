[CmdletBinding()]
param(
  [Parameter(Mandatory)] [guid] $AccountId,
  [Parameter(Mandatory)] [guid] $ConfirmAccount,
  [Parameter(Mandatory)] [switch] $ConfirmDeleteProfile
)

$ErrorActionPreference = 'Stop'
if ($AccountId -ne $ConfirmAccount -or -not $ConfirmDeleteProfile) {
  throw 'STAGE4_PROFILE_RESET_CONFIRMATION_REQUIRED'
}
$project = 'offline-reels-instagram-login-stage4'
$compose = Join-Path $PSScriptRoot '..\deploy\docker-compose.instagram-login-stage4.yml'
$envFile = Join-Path $PSScriptRoot '..\deploy\.env.instagram-login-stage4'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'STAGE4_ENV_MISSING' }
docker compose --project-name $project --env-file $envFile -f $compose run --rm --no-deps `
  -e "LOGIN_RESET_ACCOUNT_ID=$AccountId" `
  -e "LOGIN_RESET_CONFIRM_ACCOUNT=$ConfirmAccount" `
  -e 'LOGIN_RESET_DELETE_PROFILE=true' profile-reset
if ($LASTEXITCODE -ne 0) { throw 'STAGE4_PROFILE_RESET_FAILED' }
