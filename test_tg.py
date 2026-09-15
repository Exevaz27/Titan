import asyncio
import os
import sys
from dotenv import load_dotenv
load_dotenv('/home/exevaz27/titan/.env')
sys.path.insert(0, '/home/exevaz27/titan')

from integrations.telegram_bot import TelegramBotService
from core.config import config

async def run_tests():
    bot = TelegramBotService()
    print("Iniciando bot...")
    await bot.start()
    await asyncio.sleep(2)
    
    owner_id = int(config.telegram_allowed_user_id)
    print(f"Probando envio de texto a {owner_id}...")
    try:
        await bot._send_text(owner_id, "🧪 *Test de diagnóstico Titán:* Verificando funcionamiento del bot...")
        print("-> Texto enviado con éxito!")
    except Exception as e:
        print(f"-> Error enviando texto: {e}")

    # Probar sintesis y nota de voz
    print("Probando sintesis de voz...")
    try:
        from audio.tts import tts
        voice_bytes = await tts.synthesize_to_bytes("Che papá, te estoy haciendo una prueba de diagnóstico del bot de Telegram.")
        if voice_bytes:
            print(f"-> Voz sintetizada ({len(voice_bytes)} bytes). Enviando...")
            await bot._send_voice(owner_id, voice_bytes, caption="🎙️ Audio de prueba")
            print("-> Audio enviado con éxito!")
        else:
            print("-> No se generaron bytes de voz")
    except Exception as e:
        print(f"-> Error en audio: {e}")

    # Probar captura de pantalla
    print("Probando captura de pantalla...")
    try:
        from tools.system_control import system_control
        res = system_control.take_screenshot()
        print(f"-> Resultado take_screenshot: {res}")
    except Exception as e:
        print(f"-> Error en take_screenshot: {e}")

    await bot.stop()

asyncio.run(run_tests())
