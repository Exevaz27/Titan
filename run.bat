@echo off
title Titan // Satelite Windows
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [!] No se detecto el entorno virtual .venv.
    echo [*] Ejecutando instalador inicial...
    call install.bat
    if not exist "%~dp0.venv\Scripts\python.exe" (
        echo [X] Error: No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

echo ================================================================
echo   TITAN - SATELITE WINDOWS
echo ================================================================
echo.
echo [*] El nucleo de Titan vive en la PC Linux DDR3.
echo [*] Este proceso solo conecta Windows con el servidor central.
echo.
echo [!] IMPORTANTE: No cierres esta ventana mientras uses el asistente.
echo.

"%~dp0.venv\Scripts\python.exe" "%~dp0titan_satellite.py" %*

if %errorlevel% neq 0 (
    echo.
    echo [X] El asistente se detuvo con codigo de error %errorlevel%.
    pause
)