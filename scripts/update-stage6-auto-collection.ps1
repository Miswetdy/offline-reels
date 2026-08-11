[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$key = [guid]::NewGuid().Guid
$payloadFile = Join-Path ([IO.Path]::GetTempPath()) ("stage6-settings-{0}.json" -f [guid]::NewGuid())
try {
    [IO.File]::WriteAllText($payloadFile, '{"enabled":true,"target_reserve":7}', [Text.UTF8Encoding]::new($false))
    $raw = curl.exe -k --silent --show-error --fail --request PUT `
        -b $env:STAGE6_COOKIE_JAR `
        -H 'Origin: https://localhost:18443' `
        -H 'Content-Type: application/json' `
        -H "X-CSRF-Token: $env:STAGE6_CSRF_TOKEN" `
        -H "Idempotency-Key: $key" `
        --data-binary "@$payloadFile" `
        https://localhost:18443/api/instagram/collection-settings
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_SETTINGS_UPDATE_FAILED' }
    $result = $raw | ConvertFrom-Json
    if ($result.enabled -ne $true -or $result.target_reserve -ne 7 -or $result.scheduler_active -ne $false) {
        throw 'STAGE6_SETTINGS_RESPONSE_UNEXPECTED'
    }
    Write-Output 'STAGE6_SETTINGS_STORED_SCHEDULER_INACTIVE'
} finally {
    Remove-Item -LiteralPath $payloadFile -Force -ErrorAction SilentlyContinue
}
