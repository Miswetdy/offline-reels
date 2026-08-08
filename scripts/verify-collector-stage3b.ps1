param([Parameter(Mandatory = $true)][string]$ResultFile)
$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $ResultFile -ErrorAction Stop).Path
& "$PSScriptRoot\run-collector-stage3b.ps1" -VerifyResultFile $resolved
exit $LASTEXITCODE
