@echo off
REM ============================================================
REM  Satelite Titan - lanzador para Windows
REM ============================================================
REM  Como usarlo (una sola vez):
REM   1. Desde tu navegador emparejado abri http://IP-DDR3:8000/admin
REM   2. Autoriza el dispositivo "windows-satellite" como tipo PC Windows
REM   3. Toca "Descargar configuracion Windows" y guarda el archivo
REM      titan-satellite.env EN ESTA MISMA CARPETA (junto a este .bat)
REM   4. Hace doble clic en este archivo. Listo.
REM
REM  Si el satelite ya estaba corriendo, cerralo primero: este
REM  lanzador lo arranca de nuevo con la configuracion cargada.
REM ============================================================

cd /d "%~dp0"

if not exist "titan-satellite.env" (
    echo.
    echo  [ERROR] Falta titan-satellite.env en esta carpeta.
    echo  Descargalo desde el /admin de Titan y guardalo junto a este archivo.
    echo.
    pause
    exit /b 1
)

for /f "usebackq tokens=1* delims==" %%A in ("titan-satellite.env") do set "%%A=%%B"

if "%TITAN_DEVICE_TOKEN%"=="" (
    echo.
    echo  [ERROR] El archivo no trae TITAN_DEVICE_TOKEN.
    echo  Volve al /admin, autoriza de nuevo el dispositivo y descarga el archivo.
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0.."

echo.
if defined TITAN_SERVER_HOST (
    echo  Conectando satelite a %TITAN_SERVER_HOST%:%TITAN_SERVER_PORT% como %TITAN_DEVICE_ID% ...
    echo.
    python desktop\remote_satellite.py %TITAN_SERVER_HOST%
) else (
    echo  Conectando satelite como %TITAN_DEVICE_ID% ...
    echo.
    python desktop\remote_satellite.py
)

echo.
echo  El satelite se detuvo. Presiona una tecla para cerrar esta ventana.
pause >nul
