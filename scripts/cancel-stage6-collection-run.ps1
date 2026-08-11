[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$key = [guid]::NewGuid().Guid
$arguments = @(
    '-k', '--silent', '--show-error', '--fail', '--request', 'POST',
    '-b', $env:STAGE6_COOKIE_JAR,
    '-H', 'Origin: https://localhost:18443',
    '-H', "X-CSRF-Token: $env:STAGE6_CSRF_TOKEN",
    '-H', "Idempotency-Key: $key",
    "https://localhost:18443/api/instagram/collection-runs/$env:STAGE6_RUN_ID/cancel"
)
$first = & curl.exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_COLLECTION_CANCEL_FAILED' }
$second = & curl.exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'STAGE6_COLLECTION_CANCEL_REPLAY_FAILED' }
$firstResult = $first | ConvertFrom-Json
$secondResult = $second | ConvertFrom-Json
if (
    $firstResult.collection_run.status -ne 'cancelled' -or
    $secondResult.collection_run.status -ne 'cancelled'
) { throw 'STAGE6_COLLECTION_CANCEL_REPLAY_FAILED' }
Write-Output 'STAGE6_COLLECTION_CANCEL_REPLAY_OK'
