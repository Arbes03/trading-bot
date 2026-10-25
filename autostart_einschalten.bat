@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup') + '\Trading-Bot.lnk'); $s.TargetPath = '%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments = 'webseite.py --ohne-browser'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Demo-Trading-Bot (Spielgeld)'; $s.Save()"
start "" ".venv\Scripts\pythonw.exe" webseite.py --ohne-browser
echo.
echo Autostart ist eingeschaltet.
echo Bot und Webseite laufen jetzt im Hintergrund und starten nach jedem Hochfahren von selbst.
echo Webseite: http://localhost:8050
timeout /t 3 >nul
start "" http://localhost:8050
pause
