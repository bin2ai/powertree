# Builds the PowerTree Windows installer package.
#   installer\build_installer.ps1              -> PyInstaller build + zip installer
#   installer\build_installer.ps1 -SkipPyInstaller   (dist\PowerTree already built)
# Output: dist\PowerTree-Setup.zip  (portable installer: unzip anywhere or run
#         install.bat inside for Start-Menu/Desktop shortcuts)
# If Inno Setup (ISCC) is installed, also compiles dist\PowerTree-Setup.exe.

param([switch]$SkipPyInstaller)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $SkipPyInstaller) {
    & "$root\.venv\Scripts\pyinstaller.exe" installer\PowerTree.spec `
        --noconfirm --distpath dist --workpath build
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
}
if (-not (Test-Path "$root\dist\PowerTree\PowerTree.exe")) {
    throw "dist\PowerTree\PowerTree.exe missing - build first"
}

# stage: app + install/uninstall scripts + docs
$stage = "$root\dist\_stage"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item "$root\dist\PowerTree" "$stage\PowerTree" -Recurse
Copy-Item "$root\installer\install.bat" $stage
Copy-Item "$root\installer\uninstall.bat" "$stage\PowerTree"
Copy-Item "$root\README.md" "$stage\PowerTree"
if (Test-Path "$root\docs") { Copy-Item "$root\docs" "$stage\PowerTree\docs" -Recurse }

$zip = "$root\dist\PowerTree-Setup.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$stage\*" -DestinationPath $zip
Remove-Item $stage -Recurse -Force
Write-Host "OK: $zip"

# optional Inno Setup exe when ISCC is available
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                     "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if ($iscc) {
    & $iscc "$root\installer\PowerTree.iss" /DAppDist="$root\dist\PowerTree" `
        /O"$root\dist"
    Write-Host "OK: dist\PowerTree-Setup.exe (Inno Setup)"
} else {
    Write-Host "Inno Setup not found - zip installer only (PowerTree.iss ships for later)."
}
