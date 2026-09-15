import asyncio
import json
import uuid
from typing import Set, Dict
from fastapi import WebSocket
from core.state_manager import state_mgr
from core.logger import log_info, log_error, log_warning

class WebSocketHub:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.satellite_connections: Set[WebSocket] = set()
        # Futures pendientes de respuesta RPC: {request_id: asyncio.Future}
        self._pending_rpc: Dict[str, asyncio.Future] = {}
        # Métricas de telemetría de la PC Principal (Windows)
        self.last_satellite_metrics: dict = {}
        self.last_satellite_time: float = 0.0
        self.satellite_meta: dict = {}
        self.connection_meta: Dict[WebSocket, dict] = {}
        # Suscribir el hub al state_manager para reenviar todo evento
        state_mgr.subscribe(self.broadcast_event)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_meta[websocket] = {
            "role": "hud",
            "host": websocket.client.host if websocket.client else "unknown",
        }
        log_info(f"Nuevo cliente HUD conectado a la pantalla secundaria (Total: {len(self.active_connections)})")

        # Enviar estado actual y últimos mensajes inmediatamente
        try:
            snapshot = state_mgr.get_snapshot()
            await websocket.send_json({
                "type": "init_snapshot",
                "data": snapshot
            })
        except Exception as e:
            log_error(f"Error enviando snapshot inicial a WebSocket: {e}")

    def register_satellite(self, websocket: WebSocket, meta: dict = None):
        """Registra una conexión WebSocket como satélite ejecutor de Windows"""
        self.satellite_connections.add(websocket)
        self.satellite_meta = meta or {}
        self.connection_meta[websocket] = {
            **self.connection_meta.get(websocket, {}),
            **(meta or {}),
            "role": "satellite",
            "host": websocket.client.host if websocket.client else "unknown",
        }
        hostname = self.satellite_meta.get("hostname", "Windows-PC")
        log_info(f"🛰️ Satélite Windows registrado con éxito: {hostname} (Satélites activos: {len(self.satellite_connections)})")

    def update_satellite_metrics(self, metrics: dict, meta: dict = None):
        """Actualiza las métricas recibidas periódicamente del satélite Windows"""
        self.last_satellite_metrics = metrics or {}
        try:
            loop = asyncio.get_running_loop()
            self.last_satellite_time = loop.time()
        except RuntimeError:
            import time
            self.last_satellite_time = time.time()
        if meta:
            self.satellite_meta.update(meta)

    def get_satellite_metrics(self) -> dict:
        """Devuelve las últimas métricas conocidas de la PC Principal con estado de conectividad"""
        try:
            loop = asyncio.get_running_loop()
            now = loop.time()
        except RuntimeError:
            import time
            now = time.time()
        is_fresh = (now - self.last_satellite_time) < 8.0 and len(self.satellite_connections) > 0
        if is_fresh and self.last_satellite_metrics:
            res = dict(self.last_satellite_metrics)
            res["connected"] = True
            res["satellite_active"] = True
            return res
        return {
            "connected": False,
            "status": "offline",
            "hostname": self.satellite_meta.get("hostname", "PC Principal"),
            "platform": "windows",
            "message": "PC Principal desconectada o satélite inactivo"
        }

    def has_windows_satellite(self) -> bool:
        """Indica si hay al menos una PC con Windows conectada ejecutando el satélite de Titán"""
        return len(self.satellite_connections) > 0

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            log_info(f"Cliente HUD desconectado (Restantes: {len(self.active_connections)})")
        if websocket in self.satellite_connections:
            self.satellite_connections.remove(websocket)
            log_info(f"🛰️ Satélite Windows desconectado (Satélites restantes: {len(self.satellite_connections)})")
        self.connection_meta.pop(websocket, None)

    def list_connections(self) -> list[dict]:
        return [dict(meta) for ws, meta in self.connection_meta.items() if ws in self.active_connections]

    async def send_to_satellite(self, payload: dict) -> bool:
        """Envía un mensaje JSON exclusivamente a los satélites Windows conectados. Devuelve True si se envió al menos a uno."""
        if not self.satellite_connections:
            return False
        message = json.dumps(payload, ensure_ascii=False)
        sent = False
        dead = set()
        for ws in list(self.satellite_connections):
            try:
                await ws.send_text(message)
                sent = True
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.satellite_connections.discard(ws)
            self.active_connections.discard(ws)
        return sent

    def resolve_rpc(self, request_id: str, result: dict):
        """Resuelve un Future RPC pendiente cuando el satélite responde."""
        fut = self._pending_rpc.pop(request_id, None)
        if fut and not fut.done():
            fut.get_loop().call_soon_threadsafe(fut.set_result, result)

    async def call_remote(self, action: str, args: dict, timeout: float = 8.0) -> dict:
        """
        Envía una acción al satélite Windows y espera la respuesta de forma asíncrona.
        Devuelve un dict {status, message} con el resultado real del satélite.
        Si el satélite no responde en `timeout` segundos, devuelve un warning.
        """
        if not self.satellite_connections:
            return {
                "status": "warning",
                "message": "Che, no detecto la compu principal conectada. Asegurate de tener el satélite de Titán abierto en Windows."
            }

        loop = asyncio.get_running_loop()
        request_id = str(uuid.uuid4())
        fut: asyncio.Future = loop.create_future()
        self._pending_rpc[request_id] = fut

        payload = {
            "type": "remote_exec",
            "action": action,
            "args": args,
            "request_id": request_id
        }

        sent = await self.send_to_satellite(payload)
        if not sent:
            self._pending_rpc.pop(request_id, None)
            return {
                "status": "warning",
                "message": "No pude enviar la orden al satélite Windows. Puede que se haya desconectado."
            }

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_rpc.pop(request_id, None)
            log_warning(f"[RPC] Timeout esperando respuesta del satélite para '{action}' (id={request_id})")
            return {
                "status": "timeout",
                "message": f"La compu con Windows no respondió a tiempo para '{action}'. Puede que esté ocupada."
            }

    async def broadcast_event(self, event: dict):
        """Difunde un evento en formato JSON a todas las pantallas secundarias conectadas"""
        if not self.active_connections:
            return

        message = json.dumps(event, ensure_ascii=False)
        disconnected = set()
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)

        for dead_conn in disconnected:
            self.active_connections.discard(dead_conn)
            self.satellite_connections.discard(dead_conn)

ws_hub = WebSocketHub()
