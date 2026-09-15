
import asyncio
import subprocess
import speech_recognition as sr
import sys
sys.path.insert(0, '/home/exevaz27/titan')
from audio.tts import tts

async def main():
    test_phrase = "Hola Titán, ¿cuándo juega Boca el próximo partido?"
    print(f"Generando audio de prueba: '{test_phrase}'...")
    audio_bytes = await tts.synthesize_to_bytes(test_phrase)
    print(f"Audio generado: {len(audio_bytes)} bytes")

    cmd = [
        "ffmpeg", "-y", "-i", "pipe:0",
        "-f", "s16le", "-ar", "16000", "-ac", "1",
        "pipe:1"
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_pcm, err = proc.communicate(input=audio_bytes, timeout=12)
    print(f"PCM resultante: {len(raw_pcm)} bytes, exit code: {proc.returncode}")

    r = sr.Recognizer()
    audio_data = sr.AudioData(raw_pcm, 16000, 2)
    recognized = r.recognize_google(audio_data, language="es-AR")
    print(f"Texto reconocido por Google Speech: '{recognized}'")

asyncio.run(main())
