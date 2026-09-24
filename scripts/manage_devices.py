#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

from core.device_registry import registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Administra dispositivos autorizados de Titan")
    subparsers = parser.add_subparsers(dest="command", required=True)

    enroll = subparsers.add_parser("enroll", help="Da de alta un dispositivo")
    enroll.add_argument("device_id")
    enroll.add_argument("--role", action="append", choices=["api", "satellite"], required=True)

    revoke = subparsers.add_parser("revoke", help="Revoca un dispositivo")
    revoke.add_argument("device_id")

    subparsers.add_parser("list", help="Lista dispositivos sin mostrar tokens")
    args = parser.parse_args()

    if args.command == "enroll":
        token, _ = registry.enroll(args.device_id, args.role)
        # S-12: el token antes se imprimía en stdout (queda en el scrollback
        # del terminal y en cualquier log que capture la salida). Solo se
        # guarda el hash, así que este es el único momento en que existe:
        # se escribe en un archivo solo-legible por el dueño.
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in args.device_id.strip())
        token_path = Path(f"token-{safe_id}.txt")
        token_path.write_text(token + "\n", encoding="utf-8")
        os.chmod(token_path, 0o600)
        print(f"Dispositivo: {args.device_id}")
        print(f"Roles: {', '.join(args.role)}")
        print(f"Token guardado en: {token_path} (permisos 600)")
        print("Copialo al dispositivo y después borrá el archivo.")
        return 0
    if args.command == "revoke":
        if not registry.revoke(args.device_id):
            print("No existe ese dispositivo")
            return 1
        print(f"Dispositivo revocado: {args.device_id}")
        return 0

    for device_id, device in registry.list_devices().items():
        state = "activo" if device.get("enabled", True) else "revocado"
        print(f"{device_id}: {state}; roles={','.join(device.get('roles', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
