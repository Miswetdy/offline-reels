[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:STAGE6_COOKIE_JAR) -or [string]::IsNullOrWhiteSpace($env:STAGE6_CSRF_TOKEN)) {
    throw 'STAGE6_SESSION_NOT_IN_CURRENT_SESSION'
}
$key = [guid]::NewGuid().Guid
$raw = curl.exe -k --silent --show-error --fail --request POST `
    -b $env:STAGE6_COOKIE_JAR `
    -H 'Origin: https://localhost:18443' `
    -H "X-CSRF-Token: $env:STAGE6_CSRF_TOKEN" `
    -H "Idempotency-Key: $key" `
    https://localhost:18443/api/instagram/login-sessions
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_LOGIN_CREATE_FAILED' }
$result = $raw | ConvertFrom-Json
if ($null -ne $result.error -or [string]::IsNullOrWhiteSpace($result.login_session.id)) {
    throw 'STAGE6_LOGIN_RESPONSE_UNAVAILABLE'
}
$env:STAGE6_LOGIN_ID = $result.login_session.id
$env:STAGE6_LOGIN_CREATE_KEY = $key
Write-Output "STAGE6_LOGIN_SESSION_READY id=$env:STAGE6_LOGIN_ID"
