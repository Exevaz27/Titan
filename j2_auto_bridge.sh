#!/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/android-sdk/platform-tools

echo "[J2 Auto-Bridge] Monitor USB iniciado para Samsung J2..."

while true; do
    STATE=$(adb get-state 2>/dev/null)
    if [ "$STATE" = "device" ]; then
        # Verificar si reverse ya está configurado
        REV=$(adb reverse --list 2>/dev/null | grep "tcp:8000")
        if [ -z "$REV" ]; then
            echo "[J2 Auto-Bridge] J2 detectado en línea. Configurando puente USB..."
            adb reverse tcp:8000 tcp:8000
            adb shell settings put system screen_off_timeout 2147483647 2>/dev/null
            adb shell settings put global stay_on_while_plugged_in 7 2>/dev/null
            adb shell settings put system screen_brightness_mode 0 2>/dev/null
            adb shell svc power stayon true 2>/dev/null
            adb shell am start -n com.android.chrome/com.google.android.apps.chrome.Main -d "http://localhost:8000" 2>/dev/null
            echo "[J2 Auto-Bridge] Configuración aplicada exitosamente."
        fi
    fi
    sleep 5
done
