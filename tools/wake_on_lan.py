import os
import re
import socket
from typing import Any, Dict


MAC_RE = re.compile(r"^[0-9a-f]{12}$")


def _normalize_mac(mac: str) -> str:
    clean = re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()
    if not MAC_RE.fullmatch(clean):
        raise ValueError("La MAC de Windows no tiene un formato válido")
    return clean


def wake_windows_pc(mac: str = "", broadcast: str = "", port: int = 9) -> Dict[str, Any]:
    """Envía un paquete Wake-on-LAN desde el nodo Linux hacia Windows."""
    target_mac = mac.strip() or os.getenv("WINDOWS_MAC_ADDRESS", "").strip()
    target_broadcast = broadcast.strip() or os.getenv("WINDOWS_WOL_BROADCAST", "255.255.255.255").strip()
    try:
        clean_mac = _normalize_mac(target_mac)
        if not 1 <= int(port) <= 65535:
            raise ValueError("El puerto Wake-on-LAN no es válido")
        mac_bytes = bytes.fromhex(clean_mac)
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for _ in range(3):
                sock.sendto(packet, (target_broadcast, int(port)))
        return {
            "status": "success",
            "message": "Envié la señal para prender la PC Windows. Puede tardar unos segundos.",
            "mac": clean_mac,
            "broadcast": target_broadcast,
        }
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    except OSError as exc:
        return {"status": "error", "message": f"No pude enviar Wake-on-LAN: {exc}"}


def get_wol_configuration() -> Dict[str, str]:
    """Devuelve la configuración no sensible necesaria para Wake-on-LAN."""
    return {
        "mac": os.getenv("WINDOWS_MAC_ADDRESS", "").strip(),
        "broadcast": os.getenv("WINDOWS_WOL_BROADCAST", "255.255.255.255").strip(),
    }
