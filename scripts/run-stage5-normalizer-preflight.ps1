[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$postgresContainer = 'offline-reels-collector-smoke-postgres-1'
$minioContainer = 'offline-reels-collector-smoke-minio-1'
$bootstrapContainer = 'offline-reels-collector-smoke-minio-bootstrap-1'
$required = @(
    'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'MINIO_ROOT_USER',
    'MINIO_ROOT_PASSWORD', 'MINIO_BUCKET', 'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY'
)

function Get-SmokeEnvironmentValue([string]$Container, [string]$Name) {
    $line = docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' $Container |
        Where-Object { $_.StartsWith("$Name=") } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($line)) {
        throw "Missing required local Collector smoke variable: $Name"
    }
    return $line.Substring($Name.Length + 1)
}

$previous = @{}
foreach ($name in $required) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    $env:POSTGRES_DB = Get-SmokeEnvironmentValue $postgresContainer 'POSTGRES_DB'
    $env:POSTGRES_USER = Get-SmokeEnvironmentValue $postgresContainer 'POSTGRES_USER'
    $env:POSTGRES_PASSWORD = Get-SmokeEnvironmentValue $postgresContainer 'POSTGRES_PASSWORD'
    $env:MINIO_ROOT_USER = Get-SmokeEnvironmentValue $minioContainer 'MINIO_ROOT_USER'
    $env:MINIO_ROOT_PASSWORD = Get-SmokeEnvironmentValue $minioContainer 'MINIO_ROOT_PASSWORD'
    $env:MINIO_BUCKET = Get-SmokeEnvironmentValue $bootstrapContainer 'MINIO_BUCKET'
    $env:MINIO_ACCESS_KEY = Get-SmokeEnvironmentValue $bootstrapContainer 'MINIO_ACCESS_KEY'
    $env:MINIO_SECRET_KEY = Get-SmokeEnvironmentValue $bootstrapContainer 'MINIO_SECRET_KEY'
    $env:VIDEO_CURSOR_SECRET = 'stage5-read-only-placeholder-video-cursor-secret-32-chars'

    docker compose -f deploy/docker-compose.collector-smoke.yml `
        -f deploy/docker-compose.normalizer-smoke.yml `
        run --build --rm --no-deps normalizer-preflight
    $exitCode = $LASTEXITCODE
} finally {
    foreach ($name in $required) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
    Remove-Item Env:VIDEO_CURSOR_SECRET -ErrorAction SilentlyContinue
    Pop-Location
}

exit $exitCode
