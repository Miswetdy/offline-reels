[CmdletBinding()]
param([ValidateRange(1, 10)][int]$Target = 2)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:STAGE6_COOKIE_JAR) -or [string]::IsNullOrWhiteSpace($env:STAGE6_CSRF_TOKEN)) {
    throw 'STAGE6_SESSION_NOT_IN_CURRENT_SESSION'
}
$key = [guid]::NewGuid().Guid
$payload = @{ target = $Target } | ConvertTo-Json -Compress
$payloadFile = Join-Path ([IO.Path]::GetTempPath()) ("stage6-collection-{0}.json" -f [guid]::NewGuid())
try {
    [IO.File]::WriteAllText($payloadFile, $payload, [Text.UTF8Encoding]::new($false))
    $raw = curl.exe -k --silent --show-error --fail --request POST `
        -b $env:STAGE6_COOKIE_JAR `
        -H 'Origin: https://localhost:18443' `
        -H 'Content-Type: application/json' `
        -H "X-CSRF-Token: $env:STAGE6_CSRF_TOKEN" `
        -H "Idempotency-Key: $key" `
        --data-binary "@$payloadFile" `
        https://localhost:18443/api/instagram/collection-runs
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_COLLECTION_CREATE_FAILED' }
    $result = $raw | ConvertFrom-Json
    if ($null -ne $result.error -or $result.collection_run.status -ne 'queued') {
        throw 'STAGE6_COLLECTION_RESPONSE_UNAVAILABLE'
    }
    $env:STAGE6_RUN_ID = $result.collection_run.id
    $env:STAGE6_COLLECTION_CREATE_KEY = $key
} finally {
    Remove-Item -LiteralPath $payloadFile -Force -ErrorAction SilentlyContinue
}
Write-Output "STAGE6_COLLECTION_QUEUED id=$env:STAGE6_RUN_ID"
