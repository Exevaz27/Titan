#!/usr/bin/env python3
import argparse

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
        print(f"Dispositivo: {args.device_id}")
        print(f"Roles: {', '.join(args.role)}")
        print(f"Token (guardalo ahora; no se vuelve a mostrar): {token}")
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
