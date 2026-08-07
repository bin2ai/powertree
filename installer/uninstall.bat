@echo off
rem Removes PowerTree installed by install.bat (app folder + shortcuts).
setlocal
set TARGET=%LOCALAPPDATA%\PowerTree
choice /M "Remove PowerTree from %TARGET%"
if errorlevel 2 exit /b 0
powershell -NoProfile -Command ^
  "$sm = [Environment]::GetFolderPath('StartMenu') + '\Programs\PowerTree.lnk';" ^
  "$d = [Environment]::GetFolderPath('Desktop') + '\PowerTree.lnk';" ^
  "Remove-Item $sm, $d -ErrorAction SilentlyContinue"
cd /d %TEMP%
rmdir /s /q "%TARGET%"
echo PowerTree removed.
pause
