[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$payloadFile = Join-Path ([IO.Path]::GetTempPath()) ("stage6-replay-{0}.json" -f [guid]::NewGuid())
try {
    [IO.File]::WriteAllText($payloadFile, '{"target":2}', [Text.UTF8Encoding]::new($false))
    $raw = curl.exe -k --silent --show-error --fail --request POST `
        -b $env:STAGE6_COOKIE_JAR `
        -H 'Origin: https://localhost:18443' `
        -H 'Content-Type: application/json' `
        -H "X-CSRF-Token: $env:STAGE6_CSRF_TOKEN" `
        -H "Idempotency-Key: $env:STAGE6_COLLECTION_CREATE_KEY" `
        --data-binary "@$payloadFile" `
        https://localhost:18443/api/instagram/collection-runs
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_COLLECTION_REPLAY_FAILED' }
    $result = $raw | ConvertFrom-Json
    if ($result.collection_run.id -ne $env:STAGE6_RUN_ID) { throw 'STAGE6_COLLECTION_REPLAY_MISMATCH' }
    Write-Output 'STAGE6_COLLECTION_REPLAY_OK'
} finally {
    Remove-Item -LiteralPath $payloadFile -Force -ErrorAction SilentlyContinue
}
