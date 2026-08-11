[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:STAGE6_LOGIN_ID)) { throw 'STAGE6_LOGIN_ID_UNAVAILABLE' }
$key = [guid]::NewGuid().Guid
$arguments = @(
    '-k', '--silent', '--show-error', '--fail', '--request', 'POST',
    '-b', $env:STAGE6_COOKIE_JAR,
    '-H', 'Origin: https://localhost:18443',
    '-H', "X-CSRF-Token: $env:STAGE6_CSRF_TOKEN",
    '-H', "Idempotency-Key: $key",
    "https://localhost:18443/api/instagram/login-sessions/$env:STAGE6_LOGIN_ID/cancel"
)
$first = & curl.exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_LOGIN_CANCEL_FAILED' }
$second = & curl.exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_LOGIN_CANCEL_REPLAY_FAILED' }
$firstResult = $first | ConvertFrom-Json
$secondResult = $second | ConvertFrom-Json
if (
    $firstResult.login_session.id -ne $secondResult.login_session.id -or
    $firstResult.login_session.status -ne 'cancelled' -or
    $secondResult.login_session.status -ne 'cancelled'
) { throw 'STAGE6_LOGIN_CANCEL_REPLAY_FAILED' }
Write-Output 'STAGE6_LOGIN_CANCEL_REPLAY_OK'
