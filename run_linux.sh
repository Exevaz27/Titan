#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_DIR="$(pwd)"

# PIDs de instancias de Titán lanzadas desde ESTE repo.
# Detecta el proceso por la RUTA REAL del script main.py que está ejecutando,
# no solo por el directorio de trabajo: así también encuentra instancias
# arrancadas desde otra carpeta (p. ej. `python titan/main.py` desde $HOME),
# que antes quedaban vivas y hacían que el reinicio no tomara efecto.
# No toca ningún otro proceso python del sistema.
titan_pids() {
    for pid in $(pgrep -f "main\.py" 2>/dev/null || true); do
        if [[ "$pid" == "$$" ]]; then
            continue
        fi
        local cwd cmdline script_arg script_abs
        cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
        cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        # Token de la línea de comando que es el script ejecutado (termina en main.py).
        script_arg="$(echo "$cmdline" | awk '{for (i=1; i<=NF; i++) if ($i ~ /(^|\/)main\.py$/) { print $i; exit }}')"
        [[ -z "$script_arg" ]] && continue
        if [[ "$script_arg" == /* ]]; then
            script_abs="$script_arg"
        elif [[ -n "$cwd" ]]; then
            script_abs="$cwd/$script_arg"
        else
            continue
        fi
        # Normaliza ./ y ../ para comparar contra el repo.
        script_abs="$(realpath -m "$script_abs" 2>/dev/null || echo "$script_abs")"
        if [[ "$script_abs" == "$REPO_DIR/main.py" ]]; then
            echo "$pid"
        fi
    done
}

# Cerrar cualquier instancia anterior de Titán antes de arrancar.
# Si queda un Titán viejo ocupando el puerto 8000, el nuevo muere con
# "address already in use" y el navegador termina hablando con el viejo
# (sin los últimos cambios de seguridad).
old="$(titan_pids || true)"
if [[ -n "$old" ]]; then
    echo "[*] Cerrando instancia(s) anterior(es) de Titán: $(echo "$old" | tr '\n' ' ')"
    # shellcheck disable=SC2086
    kill $old 2>/dev/null || true
    # Esperar hasta 10 s a que terminen y liberen el puerto 8000.
    for _ in $(seq 1 10); do
        if [[ -z "$(titan_pids || true)" ]]; then
            break
        fi
        sleep 1
    done
    remaining="$(titan_pids || true)"
    if [[ -n "$remaining" ]]; then
        echo "[!] La instancia anterior no respondió, forzando cierre: $(echo "$remaining" | tr '\n' ' ')"
        # shellcheck disable=SC2086
        kill -9 $remaining 2>/dev/null || true
        sleep 1
    fi
    echo "[*] Instancia(s) anterior(es) cerrada(s)."
else
    echo "[*] No hay instancias anteriores de Titán corriendo."
fi

# Aviso si el puerto 8000 sigue ocupado por otro programa (no Titán).
if ! python3 -c "import socket; s = socket.socket(); s.bind(('0.0.0.0', 8000)); s.close()" 2>/dev/null; then
    echo "[!] Atención: el puerto 8000 sigue ocupado por otro programa."
    echo "    Titán va a fallar al arrancar con 'address already in use'."
fi

if [[ ! -x ".venv/bin/python" ]]; then
    echo "[!] No se encontró .venv/bin/python."
    echo "[*] Creando entorno Linux para el núcleo central de Titán..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements-linux.txt
fi

echo "[*] Iniciando el nucleo central de Titan en Linux..."
echo "[*] Panel local: http://127.0.0.1:8000/admin"
exec .venv/bin/python main.py
