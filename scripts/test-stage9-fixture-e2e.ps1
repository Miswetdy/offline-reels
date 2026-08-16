[CmdletBinding()]
param()

# Starts only an isolated synthetic fixture. It never references Collector
# smoke/production projects. It always tears down precisely this disposable
# project on success, failure, and normal Ctrl+C unwinding.
$ErrorActionPreference = 'Stop'
# Docker Compose writes normal progress to stderr.  In PowerShell 7 the
# native-command preference can otherwise turn that progress into a
# terminating NativeCommandError despite a zero Compose exit code.
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$composeFile = Join-Path $repoRoot 'deploy\docker-compose.stage9-fixture.yml'
$webRoot = Join-Path $repoRoot 'apps\web'
$testResults = Join-Path $webRoot 'tests\e2e\test-results-stage9'

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try { $listener.Start(); return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Wait-FixtureReady([string]$Origin, [int]$Port) {
    for ($attempt = 0; $attempt -lt 100; $attempt += 1) {
        & curl.exe --silent --show-error --fail --insecure --max-time 3 --resolve "localhost:$Port`:127.0.0.1" "$Origin/health/ready" | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }
    throw 'Stage 9 fixture readiness deadline elapsed.'
}

$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$projectName = "offline-reels-stage9-e2e-$suffix"
$port = Get-FreeLoopbackPort
$origin = "https://localhost:$port"
$testPassed = $false
$saved = @{}
foreach ($name in @('STAGE9_POSTGRES_PASSWORD', 'STAGE9_MINIO_PASSWORD', 'STAGE9_VIDEO_CURSOR_SECRET', 'STAGE9_FIXTURE_PAIRING_SECRET', 'STAGE9_FIXTURE_SECOND_PAIRING_SECRET', 'STAGE9_PUBLIC_ORIGIN', 'STAGE9_PORT', 'STAGE9_E2E_ORIGIN', 'STAGE9_E2E_PAIRING_SECRET', 'STAGE9_E2E_SECOND_PAIRING_SECRET')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    $env:STAGE9_POSTGRES_PASSWORD = "stage9-postgres-$suffix"
    $env:STAGE9_MINIO_PASSWORD = "stage9-minio-$suffix"
    $env:STAGE9_VIDEO_CURSOR_SECRET = "stage9-cursor-$suffix-0123456789abcdef"
    $env:STAGE9_FIXTURE_PAIRING_SECRET = "stage9-pairing-$suffix-0123456789abcdef"
    $env:STAGE9_FIXTURE_SECOND_PAIRING_SECRET = "stage9-pairing-second-$suffix-0123456789abcdef"
    $env:STAGE9_PORT = "$port"
    $env:STAGE9_PUBLIC_ORIGIN = $origin
    $env:STAGE9_E2E_ORIGIN = $origin
    $env:STAGE9_E2E_PAIRING_SECRET = $env:STAGE9_FIXTURE_PAIRING_SECRET
    $env:STAGE9_E2E_SECOND_PAIRING_SECRET = $env:STAGE9_FIXTURE_SECOND_PAIRING_SECRET
    & docker compose --project-name $projectName --file $composeFile up --build --detach
    if ($LASTEXITCODE -ne 0) { throw 'Stage 9 fixture startup failed.' }
    Wait-FixtureReady -Origin $origin -Port $port
    Push-Location $webRoot
    try {
        & npm exec -- playwright test -c tests/e2e/playwright.stage9.config.ts
        if ($LASTEXITCODE -ne 0) { throw 'Stage 9 Playwright mobile E2E failed.' }
        $testPassed = $true
    } finally { Pop-Location }
    Write-Output "STAGE9_FIXTURE_E2E_PASSED project=$projectName origin=$origin"
} finally {
    # Compose needs the fixture variables while parsing its configuration even
    # for `down`; restore the caller's environment only after cleanup.
    $cleanupFailed = $false
    # This exact, random project name owns all listed volumes/networks. It
    # cannot select Collector smoke or any retained manual fixture.
    & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
    $cleanupFailed = $LASTEXITCODE -ne 0
    if ($testPassed) {
        Remove-Item -LiteralPath $testResults -Recurse -Force -ErrorAction SilentlyContinue
    }
    foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
    if ($cleanupFailed) { throw "Stage 9 fixture cleanup failed for project=$projectName." }
}
