"""Política central de confirmaciones (P0-3).

Toda acción sensible de Titán (apagar, reiniciar, borrar, matar procesos,
mover archivos, mandar archivos por Telegram, registrar apps, ...) pasa por
acá antes de ejecutarse. La política garantiza:

- **TTL**: la confirmación pendiente vence (por defecto 120 segundos).
  Un "sí" tardío no ejecuta nada.
- **Origen**: solo se puede confirmar por el mismo canal que pidió
  la acción (voz, telegram, hud...). Un "dale" por Telegram jamás
  confirma un apagado pedido por voz.
- **Usuario/solicitante**: la confirmación está atada a quién la pidió
  (voz-local, telegram:<chat_id>, dispositivo...). Otro solicitante
  no puede confirmar ni cancelar.
- **Un solo uso**: al confirmar se consume; no se puede ejecutar dos veces.
- **Auditoría**: cada pedido, confirmación, cancelación y vencimiento
  queda registrado en el log.

El canal activo se lleva en una ContextVar: cada punto de entrada
(main.py para voz, telegram_bot.py para Telegram) lo fija al arrancar
el turno con `set_channel()`. Así `request_confirmation()` sabe
automáticamente desde dónde viene el pedido, sin cambiar firmas.
"""

from __future__ import annotations

import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from core.logger import log_info, log_warning


# ---------------------------------------------------------------------------
# Matriz de autonomía (declarativa): qué acciones exigen confirmación.
# ---------------------------------------------------------------------------

DEFAULT_TTL_SECONDS = 120

# Acción -> descripción para el usuario (acepta {args} con .format).
ACTION_DESCRIPTIONS: Dict[str, str] = {
    "shutdown": "apagar la computadora",
    "restart": "reiniciar la computadora",
    "sleep": "suspender la computadora",
    "empty_recycle_bin": "vaciar la papelera de reciclaje",
    "kill_process": "finalizar el proceso {name_or_pid}",
    "trash_file": "mandar a la papelera el archivo {file_path}",
    "move_file": "mover el archivo de {source} a {destination}",
    "send_file_to_telegram": "enviarte por Telegram el archivo {filename}",
    "register_portable_app": "registrar la aplicación '{alias}'",
    # S-6 (2026-09-17): huecos de la matriz original. Organizar mueve muchos
    # archivos; copiar/crear pisan en silencio si el destino existe; agregar
    # modifica datos existentes; gamer/frío matan procesos.
    "organize_folder": "organizar la carpeta {folder_name} (mueve archivos a subcarpetas por tipo)",
    "copy_file": "copiar {source} a {destination} (pisa el archivo existente)",
    "create_file": "crear el archivo {filename} (pisa el existente)",
    "append_to_file": "agregar texto al final del archivo {filename}",
    "optimize_pc_gaming": "activar el modo gamer (cierra programas de fondo)",
    "cool_down_pc": "activar la refrigeración (pasa a modo frío y cierra programas)",
    # 2026-09-22: fallback benigno (no es acción sensible): si la cadena VPN
    # de XuperTV falla, se le pregunta a Exequiel antes de abrir Cloudstream.
    # Reusa la maquinaria (TTL, origen, solicitante, un solo uso).
    "tv_fallback_cloudstream": "abrir Cloudstream en la tele (XuperTV no respondió)",
}

# Acción -> TTL en segundos (vencimiento de la confirmación pendiente).
ACTION_TTL: Dict[str, int] = {
    "shutdown": 120,
    "restart": 120,
    "sleep": 120,
    "empty_recycle_bin": 120,
    "kill_process": 120,
    "trash_file": 180,
    "move_file": 180,
    "send_file_to_telegram": 180,
    "register_portable_app": 180,
    "organize_folder": 180,
    "copy_file": 180,
    "create_file": 180,
    "append_to_file": 180,
    "optimize_pc_gaming": 120,
    "cool_down_pc": 120,
    "tv_fallback_cloudstream": 120,
}


def requires_confirmation(action: str) -> bool:
    """Dice si una acción está en la matriz de acciones sensibles."""
    return action in ACTION_DESCRIPTIONS


def describe_action(action: str, args: Dict) -> str:
    """Texto humano de la acción, con los argumentos interpolados."""
    template = ACTION_DESCRIPTIONS.get(action, "ejecutar esta acción sensible")
    try:
        return template.format(**{k: str(v) for k, v in (args or {}).items()})
    except (KeyError, IndexError, ValueError):
        return template


def ttl_for(action: str) -> int:
    return ACTION_TTL.get(action, DEFAULT_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Canal activo (origen + solicitante) vía ContextVar.
# ---------------------------------------------------------------------------

_current_channel: ContextVar[Tuple[str, str]] = ContextVar(
    "titan_channel", default=("voz", "voz-local")
)


def set_channel(origin: str, requester: str) -> None:
    """Fija el canal del turno actual. Lo llama cada punto de entrada."""
    _current_channel.set((origin, requester))


def current_channel() -> Tuple[str, str]:
    """Devuelve (origen, solicitante) del turno actual."""
    return _current_channel.get()


# ---------------------------------------------------------------------------
# Palabras de confirmación / cancelación (voz y texto).
# ---------------------------------------------------------------------------

_CONFIRM_EXACT = {
    "si", "sip", "confirmo", "confirmado", "dale", "de una", "deuna",
    "metele", "obvio", "claro",
}
_CONFIRM_PREFIX = ("si ", "confirmo ", "dale ", "metele ")


def _normalize(text: str) -> str:
    return (
        (text or "")
        .lower()
        .strip()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u")
        .replace("¿", "").replace("?", "")
        .replace("¡", "").replace("!", "")
        .replace(",", "").replace(".", "")
        .strip()
    )


def is_confirmation(text: str) -> bool:
    """True si el texto es una confirmación explícita."""
    norm = _normalize(text)
    return norm in _CONFIRM_EXACT or norm.startswith(_CONFIRM_PREFIX)


# ---------------------------------------------------------------------------
# Modelo y gestor central.
# ---------------------------------------------------------------------------

@dataclass
class Confirmation:
    id: str
    action: str
    args: Dict = field(default_factory=dict)
    description: str = ""
    origin: str = ""
    requester: str = ""
    created_at: float = field(default_factory=time.monotonic)
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    @property
    def expires_at(self) -> float:
        return self.created_at + self.ttl_seconds

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at

    @property
    def seconds_left(self) -> int:
        return max(0, int(self.expires_at - time.monotonic()))

    @property
    def prompt_message(self) -> str:
        mins = self.ttl_seconds // 60
        window = f"{mins} minuto{'s' if mins != 1 else ''}" if mins >= 1 else f"{self.ttl_seconds} segundos"
        return (
            f"Necesito tu confirmación para {self.description}. "
            f"Tenés {window} para responder. "
            f"Decime 'sí, confirmo' o 'cancelá'."
        )


class ConfirmationManager:
    """Gestor único de confirmaciones pendientes."""

    def __init__(self):
        # id -> Confirmation
        self._by_id: Dict[str, Confirmation] = {}
        # (origin, requester) -> id (una pendiente por canal+solicitante)
        self._latest: Dict[Tuple[str, str], str] = {}
        # (origin, requester) -> (action, momento del vencimiento):
        # para avisar "se venció" si confirman tarde (se consume al leer).
        self._recently_expired: Dict[Tuple[str, str], Tuple[str, float]] = {}

    # -- internos ---------------------------------------------------------
    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired_ids = [cid for cid, c in self._by_id.items() if c.expires_at <= now]
        for cid in expired_ids:
            conf = self._by_id.pop(cid)
            key = (conf.origin, conf.requester)
            if self._latest.get(key) == cid:
                del self._latest[key]
            self._recently_expired[key] = (conf.action, now)
            log_info(
                f"[Confirmaciones] Venció sin confirmar: {conf.action} "
                f"(origen={conf.origin}, solicitante={conf.requester})"
            )
        # Los avisos de vencimiento también caducan (10 minutos).
        old = [k for k, (_, t) in self._recently_expired.items() if now - t > 600]
        for k in old:
            del self._recently_expired[k]

    def _drop(self, conf: Confirmation) -> None:
        self._by_id.pop(conf.id, None)
        key = (conf.origin, conf.requester)
        if self._latest.get(key) == conf.id:
            del self._latest[key]

    def _matches(self, conf: Confirmation, origin: str, requester: str) -> bool:
        return conf.origin == origin and conf.requester == requester

    # -- API --------------------------------------------------------------
    def request(
        self,
        action: str,
        *,
        origin: str,
        requester: str,
        args: Optional[Dict] = None,
        description: str = "",
        ttl_seconds: Optional[int] = None,
    ) -> Confirmation:
        """Registra un pedido de confirmación. Falla cerrado si la acción
        no está en la matriz."""
        if not requires_confirmation(action):
            raise ValueError(f"Acción desconocida para confirmación: {action!r}")
        self._purge_expired()
        key = (origin, requester)
        old_id = self._latest.get(key)
        if old_id and old_id in self._by_id:
            old = self._by_id[old_id]
            self._drop(old)
            log_info(
                f"[Confirmaciones] Reemplazada pendiente anterior: {old.action} "
                f"(origen={origin}, solicitante={requester})"
            )
        conf = Confirmation(
            id=secrets.token_urlsafe(9),
            action=action,
            args=dict(args or {}),
            description=description or describe_action(action, args or {}),
            origin=origin,
            requester=requester,
            ttl_seconds=ttl_seconds or ttl_for(action),
        )
        self._by_id[conf.id] = conf
        self._latest[key] = conf.id
        log_info(
            f"[Confirmaciones] Pedido: {conf.action} id={conf.id} "
            f"(origen={origin}, solicitante={requester}, ttl={conf.ttl_seconds}s)"
        )
        return conf

    def get_pending(self, origin: str, requester: str) -> Optional[Confirmation]:
        """La confirmación pendiente vigente para este canal+solicitante."""
        self._purge_expired()
        cid = self._latest.get((origin, requester))
        return self._by_id.get(cid) if cid else None

    def expired_recently(self, origin: str, requester: str) -> Optional[str]:
        """Si una confirmación de este canal+solicitante venció hace poco,
        devuelve su acción (y consume el aviso: es de un solo uso)."""
        self._purge_expired()
        rec = self._recently_expired.pop((origin, requester), None)
        return rec[0] if rec else None

    def confirm(
        self, conf_id: str, *, origin: str, requester: str
    ) -> Optional[Confirmation]:
        """Confirma por id. Devuelve la confirmación si es válida
        (existe, vigente, mismo origen y solicitante); si no, None.
        Es de un solo uso: al confirmar se consume."""
        self._purge_expired()
        conf = self._by_id.get(str(conf_id))
        if not conf or not self._matches(conf, origin, requester):
            return None
        self._drop(conf)
        log_info(
            f"[Confirmaciones] CONFIRMADA: {conf.action} id={conf.id} "
            f"(origen={origin}, solicitante={requester})"
        )
        return conf

    def confirm_latest(
        self, origin: str, requester: str
    ) -> Optional[Confirmation]:
        """Confirma la pendiente vigente del canal (para el "sí" por voz/texto)."""
        pending = self.get_pending(origin, requester)
        if not pending:
            return None
        return self.confirm(pending.id, origin=origin, requester=requester)

    def cancel(self, conf_id: str, *, origin: str, requester: str) -> bool:
        self._purge_expired()
        conf = self._by_id.get(str(conf_id))
        if not conf or not self._matches(conf, origin, requester):
            return False
        self._drop(conf)
        log_info(
            f"[Confirmaciones] Cancelada: {conf.action} id={conf.id} "
            f"(origen={origin}, solicitante={requester})"
        )
        return True

    def cancel_latest(self, origin: str, requester: str) -> Optional[Confirmation]:
        pending = self.get_pending(origin, requester)
        if not pending:
            return None
        self._drop(pending)
        log_info(
            f"[Confirmaciones] Cancelada: {pending.action} id={pending.id} "
            f"(origen={origin}, solicitante={requester})"
        )
        return pending

    def pending_count(self) -> int:
        self._purge_expired()
        return len(self._by_id)


confirmation_manager = ConfirmationManager()


# ---------------------------------------------------------------------------
# Ejecución centralizada de acciones ya confirmadas.
# ---------------------------------------------------------------------------

def execute_action(action: str, args: Dict) -> Dict:
    """Ejecuta una acción previamente confirmada. Solo la llama quien ya
    validó la confirmación con el manager. Devuelve dict con status/message."""
    args = args or {}
    if action == "shutdown":
        from tools.system_control import system_control
        return system_control.shutdown_pc()
    if action == "restart":
        from tools.system_control import system_control
        return system_control.restart_pc()
    if action == "sleep":
        from tools.system_control import system_control
        return system_control.sleep_pc()
    if action == "empty_recycle_bin":
        from tools.system_control import system_control
        return system_control.empty_recycle_bin()
    if action == "kill_process":
        from tools.system_control import system_control
        return system_control.kill_process(args.get("name_or_pid", ""))
    if action == "trash_file":
        from tools.file_manager import file_manager
        return file_manager.trash_file(args.get("file_path", ""))
    if action == "move_file":
        from tools.file_manager import file_manager
        return file_manager.move_file(args.get("source", ""), args.get("destination", ""))
    if action == "register_portable_app":
        from tools.app_launcher import app_launcher
        return app_launcher.register_portable_app(args.get("alias", ""), args.get("file_path", ""))
    # S-6 (2026-09-17): ejecución de las acciones agregadas a la matriz.
    if action == "organize_folder":
        from tools.file_manager import file_manager
        return file_manager.organize_folder(args.get("folder_name", "Downloads"))
    if action == "copy_file":
        from tools.file_manager import file_manager
        return file_manager.copy_file(args.get("source", ""), args.get("destination", ""))
    if action == "create_file":
        from tools.file_manager import file_manager
        return file_manager.create_file(
            filename=args.get("filename", ""),
            content=args.get("content", ""),
            folder=args.get("folder", "Desktop"),
        )
    if action == "append_to_file":
        from tools.file_manager import file_manager
        return file_manager.append_to_file(
            filename=args.get("filename", ""), content=args.get("content", "")
        )
    if action == "optimize_pc_gaming":
        from tools.system_control import system_control
        return system_control.optimize_pc_gaming()
    if action == "cool_down_pc":
        from tools.system_control import system_control
        return system_control.cool_down_pc()
    # 2026-09-22: fallback benigno de la cadena VPN de XuperTV. Lo confirma
    # Exequiel con un "sí" (handle_pending_confirmation) o se cancela.
    if action == "tv_fallback_cloudstream":
        from tools.tv_control import tv_control
        return tv_control.open_app("cloudstream")
    if action == "send_file_to_telegram":
        import asyncio
        import os
        from integrations.telegram_bot import send_file_to_owner
        target = args.get("target_path", "")
        filename = args.get("filename") or os.path.basename(target)
        coro = send_file_to_owner(target, caption=f"📄 Acá tenés: {filename}")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(coro)
        else:
            asyncio.run(coro)
        return {"status": "success", "message": f"¡Listo! Te mandé el archivo '{filename}' a tu Telegram."}
    log_warning(f"[Confirmaciones] Acción desconocida al ejecutar: {action!r}")
    return {"status": "error", "message": "Acción desconocida, no se ejecutó nada."}
