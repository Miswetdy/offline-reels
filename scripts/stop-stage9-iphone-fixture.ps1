[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$StatePath
)

# Run only after explicit manual-acceptance cleanup approval. This removes the
# one Stage 9 iPhone fixture recorded by its start script; it never selects by
# wildcard and does not touch Collector smoke or other Compose projects.
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $false }

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path -LiteralPath $statePath)) { throw 'No retained Stage 9 iPhone fixture state exists.' }
$statePath = (Resolve-Path -LiteralPath $statePath).Path
$stateDirectory = Join-Path $repoRoot '.stage9-iphone-fixtures'
if (-not $statePath.StartsWith($stateDirectory + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe fixture state path: $statePath"
}
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$projectName = [string]$state.project_name
$port = [int]$state.loopback_port
if ($projectName -notmatch '^offline-reels-stage9-iphone-[a-f0-9]{12}$') { throw "Unsafe fixture project name: $projectName" }
if ($port -lt 1 -or $port -gt 65535) { throw "Unsafe fixture port: $port" }
$composeFile = Join-Path $repoRoot 'deploy\docker-compose.stage9-fixture.yml'

$saved = @{}
foreach ($name in @('STAGE9_POSTGRES_PASSWORD', 'STAGE9_MINIO_PASSWORD', 'STAGE9_VIDEO_CURSOR_SECRET', 'STAGE9_FIXTURE_PAIRING_SECRET', 'STAGE9_FIXTURE_SECOND_PAIRING_SECRET', 'STAGE9_PUBLIC_ORIGIN', 'STAGE9_PORT', 'STAGE9_CADDY_FUNNEL_HOST')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    # Compose requires nonempty interpolation values even for `down`; they are
    # parsing placeholders only and are not persisted or used for deletion.
    $env:STAGE9_POSTGRES_PASSWORD = 'stage9-cleanup-placeholder'
    $env:STAGE9_MINIO_PASSWORD = 'stage9-cleanup-placeholder'
    $env:STAGE9_VIDEO_CURSOR_SECRET = 'stage9-cleanup-cursor-0123456789abcdef0123456789abcdef'
    $env:STAGE9_FIXTURE_PAIRING_SECRET = 'stage9-cleanup-pairing-0123456789abcdef0123456789abcdef'
    $env:STAGE9_FIXTURE_SECOND_PAIRING_SECRET = 'stage9-cleanup-pairing-second-0123456789abcdef0123456789abcdef'
    $env:STAGE9_PUBLIC_ORIGIN = "https://localhost:$port"
    $env:STAGE9_PORT = "$port"
    $env:STAGE9_CADDY_FUNNEL_HOST = 'stage9-funnel.invalid'
    & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
    if ($LASTEXITCODE -ne 0) { throw "Stage 9 iPhone fixture cleanup failed for project=$projectName." }
    Remove-Item -LiteralPath $statePath -Force
    Write-Output "STAGE9_IPHONE_FIXTURE_STOPPED project=$projectName"
} finally {
    foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
}
