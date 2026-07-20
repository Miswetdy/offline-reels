[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Directory
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Directory) -or -not (Test-Path -LiteralPath $Directory -PathType Container)) {
    Write-Error "DIR must be an existing local directory."
    exit 2
}

$files = @(
    Get-ChildItem -LiteralPath $Directory -File -Filter "*.mp4" |
        Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 } |
        Sort-Object -Property Name, FullName
)
if ($files.Count -eq 0) {
    Write-Error "No regular .mp4 files were found in DIR."
    exit 2
}

& docker compose up --detach api minio
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$createdOrRestored = [System.Collections.Generic.List[string]]::new()
$alreadyExisted = [System.Collections.Generic.List[string]]::new()
$failed = [System.Collections.Generic.List[string]]::new()

foreach ($file in $files) {
    $containerPath = "/tmp/task-004-seed-$([guid]::NewGuid().ToString('N')).mp4"
    $seedExit = 1
    try {
        & docker compose cp $file.FullName "api:$containerPath"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not copy file into the API container."
        }

        $output = @(& docker compose exec --no-TTY api uv run python -m app.scripts.seed_video --file $containerPath --format json 2>&1)
        $seedExit = $LASTEXITCODE
        if ($seedExit -ne 0) {
            throw (($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine)
        }

        $result = (($output | ForEach-Object { $_.ToString() }) | Select-Object -Last 1) | ConvertFrom-Json
        if ($result.outcome -eq "already_existed") {
            $alreadyExisted.Add($file.FullName)
        }
        elseif ($result.outcome -in @("created", "restored")) {
            $createdOrRestored.Add("$($file.FullName) ($($result.outcome))")
        }
        else {
            throw "Seed command returned an unknown outcome."
        }
    }
    catch {
        $failed.Add("$($file.FullName): $($_.Exception.Message)")
    }
    finally {
        & docker compose exec --no-TTY api rm -f $containerPath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $failed.Add("$($file.FullName): could not remove temporary container file.")
        }
    }
}

Write-Host "Created/restored:"
if ($createdOrRestored.Count -eq 0) { Write-Host "  (none)" } else { $createdOrRestored | ForEach-Object { Write-Host "  $_" } }
Write-Host "Already existed:"
if ($alreadyExisted.Count -eq 0) { Write-Host "  (none)" } else { $alreadyExisted | ForEach-Object { Write-Host "  $_" } }
Write-Host "Failed:"
if ($failed.Count -eq 0) { Write-Host "  (none)" } else { $failed | ForEach-Object { Write-Host "  $_" } }

if ($failed.Count -gt 0) {
    exit 1
}
