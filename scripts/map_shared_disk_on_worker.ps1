param(
    [Parameter(Mandatory=$true)]
    [string]$MainComputer,

    [string]$ShareName = "LocalComputeShare",
    [string]$DriveLetter = "L"
)

$ErrorActionPreference = "Stop"

$sharePath = "\\$MainComputer\$ShareName"
$driveName = "$DriveLetter`:"

Write-Host "Testing $sharePath ..."
if (-not (Test-Path $sharePath)) {
    Write-Error "Cannot access $sharePath. Check Wi-Fi/Tailscale/ZeroTier, Windows sharing, firewall, and account permission."
}

if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {
    Write-Host "$driveName is already mapped."
} else {
    net use $driveName $sharePath /persistent:yes | Out-Host
}

Write-Host ""
Write-Host "Shared disk mapped."
Write-Host "UNC path: $sharePath"
Write-Host "Drive   : $driveName\"
Write-Host ""
Write-Host "For SSH jobs, UNC paths are usually safer than mapped drive letters."
