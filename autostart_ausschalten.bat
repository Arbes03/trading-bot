@echo off
powershell -NoProfile -Command "Remove-Item ([Environment]::GetFolderPath('Startup') + '\Trading-Bot.lnk') -ErrorAction SilentlyContinue"
echo.
echo Autostart ist ausgeschaltet.
echo Ein gerade laufender Bot laeuft weiter, bis du ihn auf der Webseite beendest
echo (Strategie ^& Einstellungen - "Bot ^& Webseite beenden").
pause
