@echo off
rem PowerTree portable installer: copies the app to %LOCALAPPDATA%\PowerTree
rem and creates Start-Menu + Desktop shortcuts. No admin rights needed.
setlocal
set TARGET=%LOCALAPPDATA%\PowerTree
echo Installing PowerTree to %TARGET% ...
robocopy "%~dp0PowerTree" "%TARGET%" /MIR /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
    echo Copy failed.
    pause
    exit /b 1
)
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$sm = [Environment]::GetFolderPath('StartMenu') + '\Programs';" ^
  "$s = $ws.CreateShortcut($sm + '\PowerTree.lnk');" ^
  "$s.TargetPath = '%TARGET%\PowerTree.exe'; $s.WorkingDirectory = '%TARGET%'; $s.Save();" ^
  "$d = [Environment]::GetFolderPath('Desktop');" ^
  "$s2 = $ws.CreateShortcut($d + '\PowerTree.lnk');" ^
  "$s2.TargetPath = '%TARGET%\PowerTree.exe'; $s2.WorkingDirectory = '%TARGET%'; $s2.Save()"
echo.
echo Installed. Launch PowerTree from the Start Menu or Desktop.
echo CLI: %TARGET%\powertree-cli.exe   (add to PATH if desired)
echo To remove: run %TARGET%\uninstall.bat
pause
