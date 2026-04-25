param(
    [string]$SharePath = "C:\LocalComputeShare",
    [string]$ShareName = "LocalComputeShare"
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "Run this script as Administrator on the A/main computer."
}

$inputPath = Join-Path $SharePath "input"
$outputPath = Join-Path $SharePath "outputs"
$logsPath = Join-Path $SharePath "logs"

New-Item -ItemType Directory -Force -Path $inputPath, $outputPath, $logsPath | Out-Null

$existing = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "SMB share already exists: \\$env:COMPUTERNAME\$ShareName"
} else {
    New-SmbShare -Name $ShareName -Path $SharePath -ChangeAccess "Everyone" | Out-Null
    Write-Host "Created SMB share: \\$env:COMPUTERNAME\$ShareName"
}

Write-Host ""
Write-Host "Shared disk ready."
Write-Host "A/main computer path: $SharePath"
Write-Host "Network path: \\$env:COMPUTERNAME\$ShareName"
Write-Host ""
Write-Host "Use these in the app:"
Write-Host "Input folder : \\$env:COMPUTERNAME\$ShareName\input"
Write-Host "Output folder: \\$env:COMPUTERNAME\$ShareName\outputs"
Write-Host "Logs folder  : \\$env:COMPUTERNAME\$ShareName\logs"
