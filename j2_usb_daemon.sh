#!/bin/bash
# Daemon para reconectar automáticamente el Samsung J2 vía USB
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/android-sdk/platform-tools

LAST_STATUS=""

while true; do
    STATE=$(adb get-state 2>/dev/null)
    if [ "$STATE" = "device" ]; then
        if [ "$LAST_STATUS" != "connected" ]; then
            echo "[$(date '+%T')] Samsung J2 detectado y autorizado. Configurando puente y lanzando HUD..."
            adb reverse tcp:8000 tcp:8000
            adb shell settings put system screen_off_timeout 2147483647 2>/dev/null
            adb shell settings put global stay_on_while_plugged_in 7 2>/dev/null
            adb shell settings put system screen_brightness_mode 0 2>/dev/null
            adb shell svc power stayon true 2>/dev/null
            adb shell am start -n com.android.chrome/com.google.android.apps.chrome.Main -d "http://localhost:8000" 2>/dev/null
            LAST_STATUS="connected"
            echo "[$(date '+%T')] HUD en J2 activo y listo."
        fi
    else
        LAST_STATUS=""
    fi
    sleep 4
done
