param(
    [Parameter(Mandatory=$true)]
    [string]$SharePath
)

$ErrorActionPreference = "Stop"

$testFile = Join-Path $SharePath "logs\shared-disk-test.txt"
$parent = Split-Path $testFile -Parent

if (-not (Test-Path $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

"ok from $env:COMPUTERNAME at $(Get-Date -Format s)" | Set-Content -Path $testFile -Encoding UTF8
Get-Content $testFile
Write-Host "Read/write OK: $testFile"
