[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:STAGE6_PAIRING_SECRET)) {
    throw 'STAGE6_PAIRING_SECRET_NOT_IN_CURRENT_SESSION'
}
$cookieJar = Join-Path ([IO.Path]::GetTempPath()) ("stage6-management-{0}.cookies" -f [guid]::NewGuid())
$payloadFile = Join-Path ([IO.Path]::GetTempPath()) ("stage6-management-{0}.json" -f [guid]::NewGuid())
$payload = @{ pairing_secret = $env:STAGE6_PAIRING_SECRET } | ConvertTo-Json -Compress
try {
    [IO.File]::WriteAllText($payloadFile, $payload, [Text.UTF8Encoding]::new($false))
    $raw = curl.exe -k --silent --show-error --request POST `
        -c $cookieJar `
        -H 'Origin: https://localhost:18443' `
        -H 'Content-Type: application/json' `
        --data-binary "@$payloadFile" `
        https://localhost:18443/api/management/pairing/exchange
    if ($LASTEXITCODE -ne 0) { throw 'STAGE6_PAIRING_EXCHANGE_FAILED' }
    $result = $raw | ConvertFrom-Json
    if ($null -ne $result.error) { throw ("STAGE6_PAIRING_EXCHANGE_{0}" -f $result.error.code) }
    if ([string]::IsNullOrWhiteSpace($result.csrf_token)) { throw 'STAGE6_CSRF_UNAVAILABLE' }
    $env:STAGE6_CSRF_TOKEN = $result.csrf_token
    $env:STAGE6_COOKIE_JAR = $cookieJar
    Remove-Item Env:STAGE6_PAIRING_SECRET -ErrorAction SilentlyContinue
    Write-Output 'STAGE6_MANAGEMENT_SESSION_READY'
} catch {
    Remove-Item -LiteralPath $cookieJar -Force -ErrorAction SilentlyContinue
    throw
} finally {
    Remove-Item -LiteralPath $payloadFile -Force -ErrorAction SilentlyContinue
}
