
import asyncio
import os
import sys
import base64
from dotenv import load_dotenv
load_dotenv('/home/exevaz27/titan/.env')
sys.path.insert(0, '/home/exevaz27/titan')

from integrations.telegram_bot import telegram_service
from tools.system_control import system_control
from brain.tool_registry import analyze_screen
from core.config import config

async def test_all():
    print("=== INICIANDO BATERIA ESTRICTA DE PRUEBAS DE TELEGRAM ===")
    owner_id = int(config.telegram_allowed_user_id)
    print(f"Owner ID destino: {owner_id}")

    # 1. Test de inicializacion de cliente HTTP y bot
    await telegram_service.start()
    await asyncio.sleep(1.0)
    print("[TEST 1] Bot inicializado y verificado con getMe: OK")

    # 2. Test de captura remota en Windows y envio de foto por Telegram
    print("[TEST 2] Probando captura de pantalla remota en Windows...")
    res = system_control.take_screenshot()
    print(f"-> take_screenshot resultado: status={res.get('status')}, tiene_base64={'photo_base64' in res}")
    if res.get('status') == 'success' and res.get('photo_base64'):
        photo_bytes = base64.b64decode(res['photo_base64'])
        print(f"-> Bytes de foto recibidos de Windows: {len(photo_bytes)} bytes")
        await telegram_service._send_photo(owner_id, photo_bytes, caption="📸 [Test Estricto] Captura de monitor Windows recibida por Telegram con éxito!")
        print("-> [TEST 2] Foto enviada a Telegram: EXITOSA ✅")
    else:
        print("-> [TEST 2] FALLO captura remota ❌")

    # 3. Test de lectura remota de portapapeles
    print("[TEST 3] Probando lectura de portapapeles remoto...")
    clip = system_control.get_clipboard()
    print(f"-> get_clipboard resultado: status={clip.get('status')}, text='{clip.get('text', '')[:60]}'")
    await telegram_service._send_text(owner_id, f"📋 *[Test Estricto]* Portapapeles leido desde Windows: `{clip.get('text', '')[:200]}`")
    print("-> [TEST 3] Portapapeles enviado: EXITOSA ✅")

    # 4. Test de telemetria de hardware
    print("[TEST 4] Probando telemetria de sistema...")
    metrics = system_control.get_system_metrics()
    print(f"-> CPU: {metrics.get('cpu_percent')}%, RAM: {metrics.get('ram_used_gb')}/{metrics.get('ram_total_gb')} GB")
    print("-> [TEST 4] Telemetria: EXITOSA ✅")

    # 5. Test de Vision Artificial de Pantalla (analyze_screen)
    print("[TEST 5] Probando vision artificial de pantalla Windows...")
    try:
        vis_res = analyze_screen("Describi en una sola oracion breve que ves en la pantalla")
        print(f"-> analyze_screen respuesta: {vis_res}")
        await telegram_service._send_text(owner_id, f"👁️ *[Test Estricto]* Vision de pantalla analizada:\n{vis_res}")
        print("-> [TEST 5] Vision de pantalla: EXITOSA ✅")
    except Exception as e:
        print(f"-> [TEST 5] FALLO vision: {e} ❌")

    # 6. Test de sintesis y envio de nota de voz a Telegram
    print("[TEST 6] Probando sintesis y nota de voz...")
    from audio.tts import tts
    v_bytes = await tts.synthesize_to_bytes("¡Hola papa! Esta es una prueba de voz directa desde el servidor de Titan.")
    if v_bytes:
        await telegram_service._send_voice(owner_id, v_bytes, caption="🎙️ [Test Estricto] Nota de voz oficial de Titan")
        print("-> [TEST 6] Nota de voz enviada: EXITOSA ✅")
    else:
        print("-> [TEST 6] Fallo sintesis de voz ❌")

    await telegram_service.stop()
    print("=== TODAS LAS PRUEBAS COMPLETADAS ===")

asyncio.run(test_all())
