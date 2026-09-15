@echo off
title Limpieza y Debloat - Samsung J2
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
echo   LIMPIEZA DE APLICACIONES INNECESARIAS - SAMSUNG J2
echo ================================================================
echo.
echo Esto desactivara Facebook, apps viejas de Google y bloatware
echo para liberar memoria RAM y que el celular vuele como asistente.
echo.
pause

echo.
echo [*] Desinstalando Facebook y servicios de fondo...
%ADB% shell pm uninstall -k --user 0 com.facebook.katana
%ADB% shell pm uninstall -k --user 0 com.facebook.orca
%ADB% shell pm uninstall -k --user 0 com.facebook.system
%ADB% shell pm uninstall -k --user 0 com.facebook.appmanager

echo [*] Desinstalando bloatware de Google innecesario...
%ADB% shell pm uninstall -k --user 0 com.google.android.videos
%ADB% shell pm uninstall -k --user 0 com.google.android.music
%ADB% shell pm uninstall -k --user 0 com.google.android.apps.magazines
%ADB% shell pm uninstall -k --user 0 com.google.android.apps.plus
%ADB% shell pm uninstall -k --user 0 com.google.android.apps.docs
%ADB% shell pm uninstall -k --user 0 com.google.android.talk
%ADB% shell pm uninstall -k --user 0 com.google.android.marvin.talkback

echo [*] Desinstalando apps de Microsoft...
%ADB% shell pm uninstall -k --user 0 com.microsoft.skydrive
%ADB% shell pm uninstall -k --user 0 com.microsoft.office.excel
%ADB% shell pm uninstall -k --user 0 com.microsoft.office.word
%ADB% shell pm uninstall -k --user 0 com.microsoft.office.powerpoint

echo [*] Desinstalando servicios pesados de Samsung...
%ADB% shell pm uninstall -k --user 0 com.samsung.android.email.provider
%ADB% shell pm uninstall -k --user 0 com.samsung.android.scloud.auth
%ADB% shell pm uninstall -k --user 0 com.sec.android.app.shealth

echo.
echo ================================================================
echo   [OK] LIMPIEZA COMPLETADA! Memoria RAM liberada.
echo ================================================================
pause