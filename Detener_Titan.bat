@echo off
chcp 65001 >nul
echo Deteniendo todos los servicios de Titán...

powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*titan_app.py*' -or $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo [OK] Titán se ha detenido correctamente.
timeout /t 2 >nul
