@echo off
rem Puts an "AUV-UVP6 app" shortcut on the desktop, with the app icon (double-click this file once).
rem The shortcut starts start_app.bat from this folder: run this file again if the folder is moved.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desk = [Environment]::GetFolderPath('Desktop');" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desk 'AUV-UVP6 app.lnk'));" ^
  "$s.TargetPath = (Join-Path (Get-Location) 'start_app.bat');" ^
  "$s.WorkingDirectory = (Get-Location).Path;" ^
  "$s.IconLocation = (Join-Path (Get-Location) 'auv_app.ico') + ',0';" ^
  "$s.Description = 'Starts the AUV-UVP6 pipeline app in the web browser';" ^
  "$s.Save();" ^
  "Write-Host ('Shortcut created: ' + (Join-Path $desk 'AUV-UVP6 app.lnk'))"
pause
