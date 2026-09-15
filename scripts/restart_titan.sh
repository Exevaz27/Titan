#!/bin/bash
export DISPLAY=:0
export XAUTHORITY=/home/exevaz27/.Xauthority

ICON="/home/exevaz27/titan/assets/titan_idle.png"

# Notificar inicio
notify-send -i "$ICON" "Titán Asistente" "🔄 Reiniciando el servicio Titán..." -t 3000

# Reiniciar servicio
sudo systemctl restart titan.service
sleep 2

# Comprobar estado
if systemctl is-active --quiet titan.service; then
    notify-send -i "$ICON" "Titán Asistente" "✅ ¡Titán está ACTIVO y funcionando al 100%!" -t 5000
else
    notify-send -u critical -i "$ICON" "Titán Asistente" "❌ No se pudo iniciar el servicio. Revisá los logs." -t 7000
fi

