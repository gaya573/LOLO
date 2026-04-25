$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildDir = Join-Path $Root "release_build"
$PayloadDir = Join-Path $BuildDir "payload"
$DistDir = Join-Path $Root "dist"

Remove-Item -Recurse -Force $BuildDir, $DistDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $PayloadDir, $DistDir | Out-Null

Write-Host "Building LocalCompute.exe..."
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name LocalCompute `
  --distpath $PayloadDir `
  --workpath (Join-Path $BuildDir "pyinstaller-app") `
  --specpath $BuildDir `
  --paths (Join-Path $Root "src") `
  (Join-Path $Root "installer\app_entry.py")

Copy-Item (Join-Path $Root "workers.yaml") $PayloadDir
Copy-Item (Join-Path $Root "README.md") $PayloadDir
Copy-Item (Join-Path $Root "scripts") $PayloadDir -Recurse
Copy-Item (Join-Path $Root "samples") $PayloadDir -Recurse
Copy-Item (Join-Path $Root "setup_shared_disk_on_A_admin.bat") $PayloadDir

Compress-Archive -Path (Join-Path $PayloadDir "*") -DestinationPath (Join-Path $BuildDir "payload.zip") -Force

Write-Host "Building LocalComputeMCP-Setup.exe..."
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name LocalComputeMCP-Setup `
  --add-data "$BuildDir\payload.zip;." `
  --distpath $DistDir `
  --workpath (Join-Path $BuildDir "pyinstaller-installer") `
  --specpath $BuildDir `
  (Join-Path $Root "installer\installer.py")

Write-Host ""
Write-Host "Done:"
Write-Host (Join-Path $DistDir "LocalComputeMCP-Setup.exe")
