[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$composeFile = Join-Path $repoRoot 'deploy\docker-compose.stage8-fixture.yml'

function Get-FreeLoopbackPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try { $listener.Start(); return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Invoke-FixtureApi {
    param(
        [string]$Method,
        [string]$Uri,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [object]$Body,
        [hashtable]$Headers = @{},
        [int]$Port
    )
    $cookieJar = $Session.Headers['X-Stage8-Cookie-Jar']
    $arguments = @('--silent', '--show-error', '--insecure', '--max-time', '10', '--resolve', "localhost:$Port`:127.0.0.1", '--cookie', $cookieJar, '--cookie-jar', $cookieJar, '-X', $Method, '--write-out', "`n%{http_code}")
    foreach ($header in $Headers.GetEnumerator()) { $arguments += @('-H', "$($header.Key): $($header.Value)") }
    $payloadFile = $null
    if ($null -ne $Body) {
        $payloadFile = Join-Path ([IO.Path]::GetTempPath()) "offline-reels-stage8-request-$([guid]::NewGuid().ToString('N')).json"
        [IO.File]::WriteAllText($payloadFile, ($Body | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
        $arguments += @('-H', 'Content-Type: application/json', '--data-binary', "@$payloadFile")
    }
    try { $result = @(& curl.exe @arguments $Uri) }
    finally { if ($payloadFile) { Remove-Item -LiteralPath $payloadFile -Force -ErrorAction SilentlyContinue } }
    if ($LASTEXITCODE -ne 0 -or $result.Count -lt 2) { throw "Fixture API transport failed: $Method $Uri" }
    $statusCode = [int]$result[-1]
    $json = ($result[0..($result.Count - 2)] -join "`n")
    if ($statusCode -lt 200 -or $statusCode -ge 300) {
        $safeCode = 'invalid_response'
        try { $safeCode = ($json | ConvertFrom-Json).error.code } catch {}
        throw "Fixture API returned status=$statusCode code=$safeCode for $Method $Uri"
    }
    return $json | ConvertFrom-Json
}

function Wait-FixtureReady {
    param([string]$Origin)
    for ($attempt = 0; $attempt -lt 80; $attempt += 1) {
        & curl.exe --silent --show-error --fail --insecure --max-time 3 --resolve "localhost:$($Origin.Split(':')[-1]):127.0.0.1" "$Origin/health/ready" | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }
    throw 'Fixture readiness deadline elapsed.'
}

function Wait-CatalogCount {
    param(
        [string]$Origin,
        [int]$Expected,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [int]$Port
    )
    for ($attempt = 0; $attempt -lt 80; $attempt += 1) {
        $page = Invoke-FixtureApi -Method GET -Uri "$Origin/api/videos?limit=1" -Session $Session -Body $null -Port $Port
        if ($page.items.Count -ge 1) {
            $all = @($page.items)
            $cursor = $page.next_cursor
            while ($null -ne $cursor) {
                $next = Invoke-FixtureApi -Method GET -Uri "$Origin/api/videos?limit=1&cursor=$([uri]::EscapeDataString($cursor))" -Session $Session -Body $null -Port $Port
                $all += @($next.items)
                $cursor = $next.next_cursor
            }
            if ($all.Count -eq $Expected) { return $all }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Expected $Expected ready fixture videos before the deadline."
}

$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$projectName = "offline-reels-stage8-$suffix"
$port = Get-FreeLoopbackPort
$origin = "https://localhost:$port"
$pairingSecret = "stage8-pairing-$suffix-0123456789abcdef"
$saved = @{}
foreach ($name in @('STAGE8_POSTGRES_PASSWORD', 'STAGE8_MINIO_PASSWORD', 'STAGE8_VIDEO_CURSOR_SECRET', 'STAGE8_FIXTURE_PAIRING_SECRET', 'STAGE8_PUBLIC_ORIGIN', 'STAGE8_PORT')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    $env:STAGE8_POSTGRES_PASSWORD = "stage8-postgres-$suffix"
    $env:STAGE8_MINIO_PASSWORD = "stage8-minio-$suffix"
    $env:STAGE8_VIDEO_CURSOR_SECRET = "stage8-cursor-$suffix-0123456789abcdef"
    $env:STAGE8_FIXTURE_PAIRING_SECRET = $pairingSecret
    $env:STAGE8_PORT = "$port"
    $env:STAGE8_PUBLIC_ORIGIN = $origin

    & docker compose --project-name $projectName --file $composeFile up --build --detach
    if ($LASTEXITCODE -ne 0) { throw 'Fixture startup failed.' }
    Wait-FixtureReady -Origin $origin

    $session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
    $cookieJar = Join-Path ([IO.Path]::GetTempPath()) "offline-reels-stage8-$suffix.cookies"
    $session.Headers['X-Stage8-Cookie-Jar'] = $cookieJar
    $paired = Invoke-FixtureApi -Method POST -Uri "$origin/api/management/pairing/exchange" -Session $session -Body @{ pairing_secret = $pairingSecret } -Headers @{ Origin = $origin } -Port $port
    $csrf = $paired.csrf_token
    $headers = @{ Origin = $origin; 'X-CSRF-Token' = $csrf; 'Idempotency-Key' = "fixture-login-$suffix" }
    $login = Invoke-FixtureApi -Method POST -Uri "$origin/api/instagram/login-sessions" -Session $session -Body $null -Headers $headers -Port $port
    & curl.exe --silent --show-error --fail --insecure --max-time 10 --max-redirs 2 --location --resolve "localhost:$port`:127.0.0.1" --cookie $cookieJar --cookie-jar $cookieJar $login.launch_url | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic fixture login completion failed.' }
    $refreshed = Invoke-FixtureApi -Method GET -Uri "$origin/api/management/session" -Session $session -Body $null -Port $port
    $run = Invoke-FixtureApi -Method POST -Uri "$origin/api/instagram/collection-runs" -Session $session -Body @{ target = 2 } -Headers @{ Origin = $origin; 'X-CSRF-Token' = $refreshed.csrf_token; 'Idempotency-Key' = "fixture-run-$suffix" } -Port $port
    $videos = Wait-CatalogCount -Origin $origin -Expected 2 -Session $session -Port $port
    foreach ($video in $videos) {
        $streamFile = Join-Path ([IO.Path]::GetTempPath()) "offline-reels-stage8-$suffix-$($video.id).mp4"
        & curl.exe --silent --show-error --fail --insecure --max-time 10 --resolve "localhost:$port`:127.0.0.1" --output $streamFile "$origin/api/videos/$($video.id)/stream"
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $streamFile) -or (Get-Item -LiteralPath $streamFile).Length -le 0) { throw 'Synthetic video stream is not readable.' }
        Remove-Item -LiteralPath $streamFile -Force
    }
    Write-Output "STAGE8_FIXTURE_ACCEPTED project=$projectName ready_videos=$($videos.Count) collection_run_created=$($null -ne $run.collection_run.id)"
} finally {
    & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
    foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
    if ($cookieJar) { Remove-Item -LiteralPath $cookieJar -Force -ErrorAction SilentlyContinue }
}

$remainingContainers = & docker ps -aq --filter "label=com.docker.compose.project=$projectName"
$remainingVolumes = & docker volume ls -q --filter "label=com.docker.compose.project=$projectName"
if ($remainingContainers -or $remainingVolumes) { throw "Fixture cleanup incomplete: $projectName" }
Write-Output "STAGE8_FIXTURE_CLEANUP_CONFIRMED project=$projectName"
