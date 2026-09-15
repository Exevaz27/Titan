#!/bin/bash
echo "================================================================"
echo "   CONECTANDO SAMSUNG J2 VIA USB A TITÁN (DDR3)"
echo "================================================================"

# Asegurar servidor adb activo
adb start-server >/dev/null 2>&1

STATE=$(adb get-state 2>/dev/null)

if [ "$STATE" = "device" ]; then
    echo "[OK] Dispositivo autorizado y conectado."
    
    echo "[*] 1. Configurando puente USB (localhost:8000)..."
    adb reverse tcp:8000 tcp:8000
    
    echo "[*] 2. Configurando pantalla SIEMPRE ENCENDIDA..."
    adb shell settings put system screen_off_timeout 2147483647
    adb shell settings put global stay_on_while_plugged_in 7
    adb shell settings put system screen_brightness_mode 0
    adb shell svc power stayon true
    
    echo "[*] 3. Abriendo la cara del asistente en Chrome del J2..."
    adb shell am start -n com.android.chrome/com.google.android.apps.chrome.Main -d "http://localhost:8000"
    
    echo "================================================================"
    echo "   [OK] J2 CONECTADO Y CARA DE TITÁN LANZADA EN PANTALLA!"
    echo "================================================================"
    exit 0
elif [ "$STATE" = "unauthorized" ] || [ "$STATE" = "offline" ]; then
    echo "[ALERTA] Dispositivo detectado pero en estado: $STATE"
    echo "POR FAVOR: Desbloqueá la pantalla del J2 y tocá 'Permitir depuración por USB' (marcando 'Permitir siempre')."
    exit 2
else
    DEVS=$(adb devices | grep -v "List of" | grep -v "^$")
    if [ -z "$DEVS" ]; then
        echo "[ERROR] No se detecta el J2 por ADB."
        echo "Revisá que el cable esté bien puesto y que en el celu esté activa la 'Depuración por USB'."
        exit 1
    else
        echo "[INFO] Dispositivos en lista:"
        echo "$DEVS"
        exit 3
    fi
fi
