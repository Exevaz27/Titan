#!/usr/bin/env bash
set -euo pipefail

URL="http://127.0.0.1:8000/admin"
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
elif command -v sensible-browser >/dev/null 2>&1; then
    sensible-browser "$URL" >/dev/null 2>&1 &
else
    echo "Abrí manualmente: $URL"
fi
