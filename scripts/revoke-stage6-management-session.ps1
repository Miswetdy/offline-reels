[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$key = [guid]::NewGuid().Guid
$raw = curl.exe -k --silent --show-error --fail --request DELETE `
    -b $env:STAGE6_COOKIE_JAR `
    -c $env:STAGE6_COOKIE_JAR `
    -H 'Origin: https://localhost:18443' `
    -H "X-CSRF-Token: $env:STAGE6_CSRF_TOKEN" `
    -H "Idempotency-Key: $key" `
    https://localhost:18443/api/management/session
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_SESSION_REVOKE_FAILED' }
$result = $raw | ConvertFrom-Json
if ($result.revoked -ne $true) { throw 'STAGE6_SESSION_REVOKE_RESPONSE_UNEXPECTED' }
Write-Output 'STAGE6_MANAGEMENT_SESSION_REVOKED'
