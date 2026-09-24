import asyncio
import base64
import json
import time
from urllib.parse import urljoin, urlparse
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from core.config import config
from core.state_manager import state_mgr, AssistantState
from core.logger import log_info, log_error, log_warning
from core.security import authorize_http, authorize_websocket, device_auth_is_required, device_is_valid, token_is_valid
from core.device_registry import registry
from core.pairing import pairing_manager
from core.rate_limit import RateLimiter
from server.websocket_hub import ws_hub
from tools.system_control import system_control
from tools.app_launcher import app_launcher

from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(title="Asistente de Voz Local - HUD Pantalla Secundaria")


# R-7: límite de tamaño de payloads HTTP (DoS local). Los modelos Pydantic
# validan DESPUÉS de leer el body completo en memoria: sin este freno, un
# body gigante (ej. 2 GB a /api/chat) se buferiza entero antes de ser
# rechazado por max_length. El tope cubre el endpoint más grande
# (/api/vision/analyze con image_base64 de hasta 16 MB) más overhead JSON.
MAX_HTTP_BODY_BYTES = 20 * 1024 * 1024
# R-7: tope de mensaje de texto en el WS principal. Los mensajes de control
# (prompts, triggers, telemetría) son chicos; el micrófono ya tenía su tope
# propio (MAX_MIC_CHUNK_BYTES).
WS_MAX_TEXT_BYTES = 1 * 1024 * 1024


class MaxBodySizeMiddleware:
    """Middleware ASGI puro: rechaza con 413 los bodies que superen el tope.

    Con content-length se rechaza sin leer nada; sin content-length
    (chunked) se buferiza acotado al tope y se reinyecta el body para que el
    endpoint lo lea normal. Nunca se retiene más del tope en memoria.
    """

    def __init__(self, app, max_bytes: int = MAX_HTTP_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") in ("POST", "PUT", "PATCH"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            clen = headers.get("content-length")
            if clen is not None:
                try:
                    if int(clen) > self.max_bytes:
                        resp = JSONResponse(status_code=413, content={"detail": "Payload demasiado grande"})
                        await resp(scope, receive, send)
                        return
                except ValueError:
                    pass
            else:
                # Sin content-length: leer acotado y reinyectar.
                chunks = []
                total = 0
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    if message["type"] != "http.request":
                        continue
                    chunk = message.get("body", b"")
                    total += len(chunk)
                    if total > self.max_bytes:
                        resp = JSONResponse(status_code=413, content={"detail": "Payload demasiado grande"})
                        await resp(scope, receive, send)
                        return
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
                body = b"".join(chunks)

                async def replay_receive():
                    return {"type": "http.request", "body": body, "more_body": False}

                await self.app(scope, replay_receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(MaxBodySizeMiddleware)


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheMiddleware)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """S-8: headers de seguridad HTTP en todas las respuestas.

    El CSP permite los scripts inline (admin.html e index.html los usan),
    el CDN de jsdelivr y Google Fonts que ya usa el HUD, y data: para el
    QR de emparejamiento; bloquea object-src, base-uri ajena y framing
    cruzado (reforzado también con X-Frame-Options).
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'self'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)


class AuthMiddleware(BaseHTTPMiddleware):
    """P0: exige autenticación en /api/* (salvo /api/pair/claim) y en /static/*.

    Las páginas /pair y /healthz quedan públicas a propósito: /pair es la
    puerta de entrada para emparejar un dispositivo nuevo con el código de
    6 dígitos, y /healthz es solo para monitoreo.

    Nota: la excepción de authorize_http se convierte acá en respuesta 401,
    porque los middlewares corren por fuera del manejador de excepciones
    del router y si no el cliente recibiría un 500.
    """
    async def dispatch(self, request, call_next):
        path = request.url.path
        needs_auth = (path.startswith("/api/") and path != "/api/pair/claim") or path.startswith("/static/")
        if needs_auth:
            try:
                authorize_http(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)


app.add_middleware(AuthMiddleware)

# P0: cookies de dispositivos emparejados con validez larga (1 año). El J2 y
# otros HUD quedan siempre prendidos; una sesión de 24 h obligaría a
# re-emparejar a mano cada día. La revocación se hace desde /admin en
# cualquier momento.
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 3600

# P0: freno de fuerza bruta para /api/pair/claim (código de 6 dígitos).
_pair_limiter = RateLimiter(max_attempts=5, window_seconds=600, lockout_seconds=600)

STATIC_DIR = Path(__file__).resolve().parent / "static"

import base64
from pydantic import BaseModel

# Modelos para endpoints
MAX_PROMPT_LENGTH = 8_000
MAX_IMAGE_BASE64_LENGTH = 16 * 1024 * 1024
MAX_MIC_CHUNK_BYTES = 64 * 1024
MAX_ACTIVE_MICS = 2


class ChatPrompt(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)

class ApiKeyUpdate(BaseModel):
    api_key: str = Field(min_length=20, max_length=512)

class AppRegister(BaseModel):
    alias: str
    path: str

class PowerPlanRequest(BaseModel):
    plan_mode: str = "balanced"

class VisionRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=MAX_IMAGE_BASE64_LENGTH)
    question: Optional[str] = Field(default="", max_length=MAX_PROMPT_LENGTH)

class ScreenAnalyzeRequest(BaseModel):
    question: Optional[str] = Field(default="", max_length=MAX_PROMPT_LENGTH)

class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    width: Optional[int] = Field(default=1024, ge=256, le=2048)
    height: Optional[int] = Field(default=1024, ge=256, le=2048)

class PairingClaim(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

# Callback global para procesar comandos recibidos por web
_command_processor = None

def set_command_processor(processor):
    global _command_processor
    _command_processor = processor

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await authorize_websocket(websocket, role="ws")
    await ws_hub.connect(websocket)
    try:
        while True:
            # Escuchar mensajes enviados desde la interfaz web (botones, triggers, prompts)
            # R-7: tope de tamaño antes de parsear; sin esto un mensaje gigante
            # se buferiza y parsea entero en memoria (DoS local).
            raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > WS_MAX_TEXT_BYTES:
                log_warning("[Seguridad] Mensaje WS descartado por tamaño.")
                await websocket.close(code=1009, reason="Mensaje demasiado grande")
                break
            data = json.loads(raw)
            msg_type = data.get("type")
            
            if msg_type == "register_satellite":
                token = websocket.headers.get("x-titan-token", "").strip()
                device_id = websocket.headers.get("x-titan-device-id", "").strip()
                authorized = device_is_valid(device_id, token, ("satellite",)) if device_auth_is_required() else token_is_valid(token, "satellite")
                if not authorized:
                    await websocket.close(code=1008, reason="Token de satélite inválido")
                    return
                ws_hub.register_satellite(websocket, data)
                # P0-4 — Autenticación mutua: el satélite desafía al servidor
                # a probar que conoce el token (challenge-response HMAC).
                # Sin este proof, un servidor impostor en la LAN podría
                # darle órdenes al satélite y este las obedecería a ciegas.
                # Además se guarda el token de esta conexión para firmar
                # cada remote_exec (se borra al desconectar).
                nonce = data.get("auth_nonce", "")
                if nonce and token:
                    from core import rpc_auth
                    ws_hub.connection_meta[websocket]["rpc_token"] = token
                    await websocket.send_json({
                        "type": "satellite_auth_ok",
                        "server_proof": rpc_auth.server_proof(token, nonce),
                    })
            elif msg_type == "satellite_telemetry":
                # S-7: la telemetría solo la puede reportar un satélite
                # registrado (pasó por register_satellite con token válido).
                # Antes cualquier cliente WS autenticado (ej. un navegador
                # con token de HUD) podía inyectar métricas falsas.
                if websocket not in ws_hub.satellite_connections:
                    log_warning("[Seguridad] Telemetría descartada: el remitente no es un satélite registrado.")
                else:
                    metrics = data.get("metrics", {})
                    hostname = data.get("hostname", "Windows-PC")
                    ws_hub.update_satellite_metrics(metrics, meta={"hostname": hostname})
            elif msg_type == "record_activity":
                state_mgr.record_activity(trigger_wake=bool(data.get("trigger_wake", True)))
            elif msg_type == "trigger_listen":
                state_mgr.record_activity(trigger_wake=True)
                from audio.listener import listener
                from audio.stream_listener import stream_listener
                listener.trigger_manual_listen()
                stream_listener.trigger_manual_listen()
            elif msg_type in ["chat_prompt", "command"]:
                prompt_text = data.get("text", "")
                norm_prompt = prompt_text.lower()
                is_rest_cmd = any(w in norm_prompt for w in ["mate", "descans", "dormi", "mimir", "siesta", "pausa", "amargo"])
                if not is_rest_cmd and state_mgr.inactivity_stage not in ["mate", "drowsy", "sleeping"]:
                    state_mgr.record_activity(trigger_wake=True)
                if prompt_text and _command_processor:
                    asyncio.create_task(_command_processor(prompt_text))
            elif msg_type == "set_stage":
                target_stage = data.get("stage", "idle")
                from tools.system_control import system_control
                system_control.set_inactivity_stage(target_stage)
            elif msg_type == "test_voice":
                from audio.tts import tts
                asyncio.create_task(tts.speak("¿Qué hacés, papá? Acá estoy listo para darte una mano con la compu."))
            elif msg_type in ["interrupt", "barge_in", "stop_speaking"]:
                from audio.tts import tts
                from audio.stream_listener import stream_listener
                tts.stop()
                stream_listener.interrupt_speech()
            elif msg_type == "switch_view":
                view_name = data.get("view", "orb")
                state_mgr.emit_view_switch(view_name)
            elif msg_type == "set_mode":
                target_mode = data.get("mode", "normal")
                from brain.gemini_client import brain
                brain.set_mode(target_mode)
            elif msg_type == "set_hands_free":
                enabled = data.get("enabled", True)
                state_mgr.set_hands_free(enabled)
            elif msg_type == "j2_photo_result":
                from tools.j2_camera import j2_camera
                j2_camera.handle_photo_result(data)
            elif msg_type == "cool_down_pc":
                # P0-5 — En modos restrictivos (rebelde/pibes) no se ejecutan acciones.
                from core.mode_policy import actions_blocked
                if actions_blocked():
                    await websocket.send_json({"type": "thermal_action_result", "action": "cool_down_pc",
                                               "result": {"status": "error", "message": "Bloqueado por el modo activo."}})
                else:
                    from tools.system_control import system_control
                    res = system_control.cool_down_pc()
                    await websocket.send_json({"type": "thermal_action_result", "action": "cool_down_pc", "result": res})
            elif msg_type == "set_power_plan":
                # P0-5 — En modos restrictivos (rebelde/pibes) no se ejecutan acciones.
                from core.mode_policy import actions_blocked
                if actions_blocked():
                    await websocket.send_json({"type": "thermal_action_result", "action": "set_power_plan",
                                               "result": {"status": "error", "message": "Bloqueado por el modo activo."}})
                else:
                    plan = data.get("plan_mode", "balanced")
                    from tools.system_control import system_control
                    res = system_control.set_power_plan(plan)
                    await websocket.send_json({"type": "thermal_action_result", "action": "set_power_plan", "result": res})
            elif msg_type == "rpc_reply":
                # El satélite Windows respondió a una llamada RPC remota
                request_id = data.get("request_id", "")
                result = data.get("result", {"status": "success", "message": "Hecho."})
                if request_id:
                    ws_hub.resolve_rpc(request_id, result)
            elif msg_type == "image_generate":
                prompt_text = data.get("prompt", "")
                if prompt_text:
                    from tools.image_generator import image_generator
                    from audio.tts import tts
                    await ws_hub.broadcast_event({"type": "image_generating", "prompt": prompt_text})
                    res = await image_generator.generate(prompt_text)
                    if res.get("status") == "success":
                        await ws_hub.broadcast_event({
                            "type": "image_generated",
                            "url": res["url"],
                            "filename": res["filename"],
                            "prompt": res["prompt"],
                            "enriched_prompt": res.get("enriched_prompt", ""),
                            "timestamp": time.strftime("%H:%M")
                        })
                        spoken_msg = f"¡Listo, papá! Ahí te generé la imagen de {prompt_text}. La podés ver y descargar en la pantalla de Control."
                        asyncio.create_task(tts.speak(spoken_msg))
    except WebSocketDisconnect:
        pass  # desconexión limpia: el finally de abajo la registra
    except Exception as e:
        log_error(f"Error en socket: {e}")
    finally:
        # F6: desconectar SIEMPRE, también si el handler salió con break
        # (mensaje gigante, close 1009) o return (token de satélite inválido,
        # close 1008). Antes esos caminos dejaban el socket muerto en
        # active_connections y su connection_meta colgada para siempre.
        ws_hub.disconnect(websocket)

latest_mic_id: int = 0
active_mic_count: int = 0
# F5: el chequeo del tope y el incremento no eran atómicos (había un await
# en el medio): dos celulares conectando a la vez podían colarse los dos.
_mic_lock = asyncio.Lock()

def has_active_mobile_mic() -> bool:
    global active_mic_count
    return active_mic_count > 0

@app.websocket("/ws/mic")
async def websocket_mic_endpoint(websocket: WebSocket):
    global latest_mic_id, active_mic_count
    await authorize_websocket(websocket, role="api")
    async with _mic_lock:
        if active_mic_count >= MAX_ACTIVE_MICS:
            await websocket.close(code=1013, reason="Límite de micrófonos alcanzado")
            return
        await websocket.accept()
        latest_mic_id += 1
        active_mic_count += 1
        my_id = latest_mic_id
    log_info(f"[Mic Celular] Transmisión #{my_id} conectada vía WebSocket (Activos: {active_mic_count})")
    from audio.stream_listener import stream_listener
    try:
        while True:
            chunk = await websocket.receive_bytes()
            if len(chunk) > MAX_MIC_CHUNK_BYTES:
                await websocket.close(code=1009, reason="Bloque de audio demasiado grande")
                return
            if my_id == latest_mic_id:
                stream_listener.process_pcm_chunk(chunk)
    except WebSocketDisconnect:
        log_info(f"[Mic Celular] Transmisión #{my_id} desconectada")
    except Exception as e:
        log_info(f"[Mic Celular] Transmisión #{my_id} terminada: {e}")
    finally:
        active_mic_count = max(0, active_mic_count - 1)

@app.post("/api/vision/analyze")
async def analyze_vision_endpoint(data: VisionRequest):
    from brain.gemini_client import brain
    from audio.tts import tts
    try:
        clean_b64 = data.image_base64.split(",")[-1]
        img_bytes = base64.b64decode(clean_b64)
        reply = await brain.analyze_vision(img_bytes, data.question or "")
        asyncio.create_task(tts.speak(reply))
        return {"status": "success", "reply": reply}
    except Exception as e:
        # S-MED-8: no exponer el detalle interno (puede traer fragmentos de
        # la API o trazas); se loguea en el servidor y se devuelve genérico.
        log_error(f"[Vision] /api/vision/analyze falló: {e!r}")
        raise HTTPException(status_code=500, detail="Error interno analizando la imagen.")

@app.get("/api/status")
async def get_status():
    return {
        "status": state_mgr.current_state,
        "detail": state_mgr.state_detail,
        "metrics": system_control.get_system_metrics(),
        "has_api_key": bool(config.gemini_api_key),
        "voice": config.tts_voice,
        "hotkey": config.hotkey
    }

@app.get("/api/metrics")
async def get_metrics():
    primary = ws_hub.get_satellite_metrics()
    ddr3 = system_control.get_system_metrics()
    ddr3["is_server"] = True
    ddr3["server_label"] = "Servidor Titán (DDR3)"

    base = primary if primary.get("connected") else ddr3
    result = dict(base)
    result["status"] = "success"
    result["primary"] = primary
    result["ddr3"] = ddr3
    return result

@app.post("/api/pc/thermal/cool-down")
async def pc_thermal_cool_down():
    from tools.system_control import system_control
    res = system_control.cool_down_pc()
    return res

@app.post("/api/pc/thermal/power-plan")
async def pc_thermal_power_plan(req: PowerPlanRequest):
    from tools.system_control import system_control
    res = system_control.set_power_plan(req.plan_mode)
    return res

@app.post("/api/pc/voice/toggle")
async def pc_voice_toggle():
    from tools.system_control import system_control
    res = system_control.toggle_pc_voice()
    return res

@app.post("/api/pc/screen/analyze")
async def pc_screen_analyze_endpoint(req: ScreenAnalyzeRequest = ScreenAnalyzeRequest()):
    from brain.gemini_client import brain
    from audio.tts import tts
    from server.websocket_hub import ws_hub

    if not ws_hub.has_windows_satellite():
        raise HTTPException(status_code=503, detail="La PC Principal (Windows) no está conectada.")

    try:
        res = await ws_hub.call_remote("take_screenshot", {}, timeout=10.0)
        b64 = res.get("photo_base64")
        if not b64:
            raise HTTPException(status_code=500, detail="No se pudo obtener la captura de pantalla de Windows (¿pantalla bloqueada o apagada?).")

        clean_b64 = b64.split(",")[-1]
        img_bytes = base64.b64decode(clean_b64)
        q = req.question or "Describí qué hay en la pantalla y qué error o información se muestra"
        reply = await brain.analyze_screen(img_bytes, question=q)
        asyncio.create_task(tts.speak(reply))
        return {
            "status": "success",
            "reply": reply,
            "photo_base64": f"data:image/jpeg;base64,{clean_b64}"
        }
    except HTTPException:
        raise
    except Exception as e:
        # S-MED-8: no exponer el detalle interno; se loguea en el servidor.
        log_error(f"[Vision] analyze-screen falló: {e!r}")
        raise HTTPException(status_code=500, detail="Error interno analizando la pantalla.")

@app.post("/api/image/generate")
async def generate_image_endpoint(req: ImageGenerateRequest):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacío")
    from tools.image_generator import image_generator
    from audio.tts import tts
    from server.websocket_hub import ws_hub

    # 1. Avisar por WS que se está generando la imagen
    await ws_hub.broadcast_event({
        "type": "image_generating",
        "prompt": req.prompt.strip()
    })

    res = await image_generator.generate(req.prompt.strip(), width=req.width or 1024, height=req.height or 1024)
    if res.get("status") == "success":
        # Broadcast al HUD para que la inserte en el feed de chat
        event_payload = {
            "type": "image_generated",
            "url": res["url"],
            "filename": res["filename"],
            "prompt": res["prompt"],
            "enriched_prompt": res.get("enriched_prompt", ""),
            "timestamp": time.strftime("%H:%M")
        }
        await ws_hub.broadcast_event(event_payload)
        spoken_msg = f"¡Listo, papá! Ahí te generé la imagen de {req.prompt.strip()}. La podés ver y descargar en la pantalla de Control."
        asyncio.create_task(tts.speak(spoken_msg))
        return {
            "status": "success",
            "url": res["url"],
            "filename": res["filename"],
            "prompt": res["prompt"],
            "enriched_prompt": res.get("enriched_prompt", ""),
            "elapsed": res.get("elapsed", 0)
        }
    else:
        raise HTTPException(status_code=500, detail=res.get("message", "Error generando imagen"))

def validate_wallpaper_url(image_url: str) -> str:
    """P0-4 — Valida la URL de imagen para /api/pc/wallpaper/set.

    Acepta rutas locales del propio servidor ("/...": imágenes generadas
    por Titán) o URLs http/https con host. Rechaza otros esquemas
    (file://, ftp://, javascript:, ...) y URLs absurdamente largas.
    Devuelve la URL normalizada o lanza ValueError.
    """
    url = (image_url or "").strip()
    if not url:
        raise ValueError("Falta el parámetro image_url")
    if len(url) > 2048:
        raise ValueError("URL de imagen demasiado larga")
    if url.startswith("/"):
        return url  # imagen generada por el propio servidor
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("URL de imagen inválida: solo se permiten http/https")
    return url


@app.post("/api/pc/wallpaper/set")
async def pc_set_wallpaper(data: Dict[str, Any]):
    from server.websocket_hub import ws_hub
    if not ws_hub.has_windows_satellite():
        raise HTTPException(status_code=503, detail="La PC Principal (Windows) no está conectada.")
    img_url = data.get("image_url", "")
    # P0-4 — Validar la URL antes de pedirle al satélite que la descargue.
    try:
        img_url = validate_wallpaper_url(img_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if img_url.startswith("/"):
        host_ip = "192.168.100.5"
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            host_ip = s.getsockname()[0]
            s.close()
        except Exception:
            host_ip = "192.168.100.5"
        full_url = f"http://{host_ip}:{config.server_port}{img_url}"
    else:
        full_url = img_url
    res = await ws_hub.call_remote("set_wallpaper", {"url": full_url}, timeout=15.0)
    return res

@app.post("/api/chat")
async def send_chat_prompt(prompt: ChatPrompt):
    if not prompt.message.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    if _command_processor:
        # Ejecutar en segundo plano para que el usuario reciba la respuesta por voz y WS
        asyncio.create_task(_command_processor(prompt.message))
        return {"status": "enqueued", "message": prompt.message}
    raise HTTPException(status_code=500, detail="Procesador de comandos no configurado")

@app.post("/api/trigger")
async def trigger_listening():
    from audio.listener import listener
    from audio.stream_listener import stream_listener
    listener.trigger_manual_listen()
    stream_listener.trigger_manual_listen()
    return {"status": "listening_triggered"}

@app.post("/api/tts/test")
async def test_tts_voice():
    from audio.tts import tts
    asyncio.create_task(tts.speak("¡Buenas! Soy tu asistente de Windows. Si necesitás abrir algo o buscar archivos, pegame el grito nomás."))
    return {"status": "speaking"}

@app.get("/api/apps")
async def get_apps():
    return {
        "catalog": app_launcher.list_catalog_apps(),
        "scan_folders": config.portable_folders
    }

@app.post("/api/apps")
async def register_app(app_data: AppRegister):
    res = app_launcher.register_portable_app(app_data.alias, app_data.path)
    return res

@app.post("/api/key")
async def update_key(key_data: ApiKeyUpdate):
    from brain.gemini_client import brain
    brain.update_api_key(key_data.api_key)
    return {"status": "success", "message": "Clave de Gemini API guardada correctamente"}

@app.get("/api/mode")
async def get_mode_endpoint():
    from brain.gemini_client import brain
    return {
        "mode": getattr(brain, "current_mode", "normal"),
        "is_rebel_mode": getattr(brain, "is_rebel_mode", False),
        "last_speaker": state_mgr.last_speaker
    }

@app.post("/api/mode")
async def set_mode_endpoint(payload: dict):
    from brain.gemini_client import brain
    target_mode = payload.get("mode", "normal")
    brain.set_mode(target_mode)
    return {
        "status": "success",
        "mode": getattr(brain, "current_mode", "normal"),
        "is_rebel_mode": getattr(brain, "is_rebel_mode", False)
    }

@app.get("/api/camera/j2/photo")
async def get_j2_camera_photo(facing: Optional[str] = None):
    from tools.j2_camera import j2_camera
    from fastapi.responses import Response
    photo_bytes = await j2_camera.capture_photo(facing_mode=facing, timeout=7.0)
    if photo_bytes:
        return Response(content=photo_bytes, media_type="image/jpeg")
    raise HTTPException(status_code=504, detail="No se pudo capturar foto del Samsung J2 (¿pantalla conectada?)")

@app.post("/api/camera/j2/toggle")
async def toggle_j2_camera_endpoint():
    from tools.j2_camera import j2_camera
    label = j2_camera.toggle_facing()
    return {"status": "success", "facing": j2_camera.current_facing, "label": label}

@app.get("/api/security/status")
async def get_security_status_endpoint():
    from tools.surveillance_service import surveillance_service
    from tools.system_control import system_control
    loop = asyncio.get_running_loop()
    pc_info = await loop.run_in_executor(None, system_control.get_pc_security_info)
    surv_st = surveillance_service.get_status()
    return {
        "status": "success",
        "surveillance": surv_st,
        "pc_security": pc_info
    }


@app.get("/healthz")
async def health_check():
    return {"status": "ok", "service": "titan"}


@app.get("/api/admin/devices")
async def admin_list_devices(request: Request):
    authorize_http(request, role="admin")
    return {
        "registered": registry.list_devices(),
        "connected": ws_hub.list_connections(),
    }


@app.post("/api/admin/devices/enroll")
async def admin_enroll_device(payload: dict, request: Request):
    authorize_http(request, role="admin")
    device_id = str(payload.get("device_id", "")).strip()
    roles = payload.get("roles", [])
    # S-4: existe el rol "admin"; solo un admin puede enrolar.
    if not isinstance(roles, list) or not all(role in {"api", "satellite", "admin"} for role in roles):
        raise HTTPException(status_code=400, detail="Roles inválidos")
    try:
        token, device = registry.enroll(device_id, roles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    requested_base = str(payload.get("base_url", "")).strip()
    base_url = requested_base or str(request.base_url).rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="La dirección de Titán no es válida")
    # P0: la URL de emparejamiento YA NO lleva el token en el query string
    # (queda en historial y logs). Se ingresa el código en /pair.
    pairing_url = f"{base_url}/pair"
    qr_data_uri = None
    try:
        import io
        import qrcode
        image = qrcode.make(pairing_url)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        qr_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except ImportError:
        log_warning("[Dispositivos] Falta qrcode; se entrega el enlace sin QR")
    return {
        "device_id": device_id,
        "roles": device["roles"],
        "token": token,
        "pairing_url": pairing_url,
        "qr_data_uri": qr_data_uri,
        "pairing_code": pairing_manager.create(device_id, token),
    }


@app.post("/api/pair/claim")
async def claim_pairing_code(pairing: PairingClaim, request: Request):
    # P0: rate limiting por IP contra fuerza bruta del código de 6 dígitos.
    client_ip = request.client.host if request.client else "desconocida"
    if _pair_limiter.is_blocked(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Probá de nuevo más tarde.",
            headers={"Retry-After": str(_pair_limiter.retry_after(client_ip))},
        )
    claimed = pairing_manager.claim(pairing.code)
    if not claimed:
        _pair_limiter.register_failure(client_ip)
        raise HTTPException(status_code=401, detail="Código inválido o vencido")
    _pair_limiter.register_success(client_ip)

    if claimed["kind"] == "setup":
        # Código de configuración inicial: enrolar un dispositivo nuevo.
        import secrets as _secrets
        device_id = f"navegador-{_secrets.token_hex(3)}"
        token, _device = registry.enroll(device_id, claimed["roles"])
        log_info(f"[Seguridad] Dispositivo enrolado con código de configuración inicial: {device_id}")
    else:
        device_id, token = claimed["device_id"], claimed["token"]

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("titan_token", token, httponly=True, samesite="strict", max_age=DEVICE_COOKIE_MAX_AGE)
    response.set_cookie("titan_device_id", device_id, httponly=True, samesite="strict", max_age=DEVICE_COOKIE_MAX_AGE)
    return response


@app.post("/api/admin/devices/{device_id}/revoke")
async def admin_revoke_device(device_id: str, request: Request):
    authorize_http(request, role="admin")
    if not registry.revoke(device_id):
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return {"status": "success", "device_id": device_id, "enabled": False}

# Servir archivos estáticos del HUD
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_index(request: Request):
    # P0: el HUD exige autenticación. Sin cookie de dispositivo emparejado
    # no se sirve la página (antes era pública para toda la LAN).
    # P0: ya no se aceptan tokens en el query string.
    authorize_http(request)
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({"message": "HUD Frontend no encontrado en /static"})


@app.get("/admin")
async def serve_admin(request: Request):
    # P0: sin bypass de loopback. El panel admin exige autenticación siempre.
    # S-4: además exige rol "admin" (un HUD común ya no puede ni verlo).
    authorize_http(request, role="admin")
    admin_path = STATIC_DIR / "admin.html"
    if admin_path.exists():
        return FileResponse(admin_path)
    return JSONResponse({"message": "Gestor de dispositivos no encontrado"}, status_code=404)


@app.get("/pair")
async def serve_pair():
    pair_path = STATIC_DIR / "pair.html"
    if pair_path.exists():
        return FileResponse(pair_path)
    return JSONResponse({"message": "Emparejamiento no disponible"}, status_code=404)
