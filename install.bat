@echo off
title Instalador - Satelite Windows de Titan
cd /d "%~dp0"

echo ================================================================
echo   INSTALADOR - SATELITE WINDOWS DE TITAN
echo ================================================================
echo.

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3.11
    goto CREATE_VENV
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto CREATE_VENV
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto CREATE_VENV
)

echo [X] Error: No se encontro Python 3.11. Ejecuta: winget install Python.Python.3.11
pause
exit /b 1

:CREATE_VENV
echo [*] Creando entorno virtual .venv con %PYTHON_CMD%...
%PYTHON_CMD% -m venv "%~dp0.venv"
if %errorlevel% neq 0 (
    echo [X] Error al crear el entorno virtual.
    pause
    exit /b 1
)

echo [*] Actualizando pip e instalando dependencias...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements-windows.txt"

if %errorlevel% equ 0 (
    echo.
    echo ================================================================
    echo   [OK] INSTALACION COMPLETADA CON EXITO!
    echo   Ahora podes iniciar el asistente ejecutando: run.bat
    echo ================================================================
) else (
    echo [X] Ocurrio un problema durante la instalacion de paquetes.
)

pause