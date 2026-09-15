@echo off
title Conectar Samsung J2 - Asistente
cd /d "%~dp0"

set ADB="%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe"

if not exist %ADB% (
    where adb >nul 2>nul
    if %errorlevel% equ 0 (
        set ADB=adb
    ) else (
        echo [X] No se encontro adb.exe
        pause
        exit /b 1
    )
)

echo ================================================================
echo   CONECTANDO SAMSUNG J2 VIA USB
echo ================================================================
echo.

echo [*] Comprobando dispositivo...
%ADB% devices

echo.
echo [*] 1. Configurando puente USB (localhost:8000)...
%ADB% reverse tcp:8000 tcp:8000

echo [*] 2. Configurando pantalla SIEMPRE ENCENDIDA (sin apagado automatico)...
%ADB% shell settings put system screen_off_timeout 2147483647
%ADB% shell settings put global stay_on_while_plugged_in 7
%ADB% shell settings put system screen_brightness_mode 0
%ADB% shell svc power stayon true

echo [*] 3. Abriendo la cara del asistente en Chrome del J2 (Servidor DDR3 192.168.100.5:8000)...
%ADB% shell am start -n com.android.chrome/com.google.android.apps.chrome.Main -d "http://192.168.100.5:8000"

echo.
echo ================================================================
echo   [OK] J2 CONECTADO Y CONFIGURADO CORRECTAMENTE!
echo ================================================================
echo.
pause