#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

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
