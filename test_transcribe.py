
import subprocess
import os
import sys
from dotenv import load_dotenv
load_dotenv('/home/exevaz27/titan/.env')
sys.path.insert(0, '/home/exevaz27/titan')

from google import genai
from google.genai import types

# 1. Generar audio de prueba con Edge-TTS
from audio.tts import tts
import asyncio

async def test():
    phrase = "Hola Titán, ¿cuándo juega Boca el próximo partido?"
    raw_audio = await tts.synthesize_to_bytes(phrase)
    print(f"Audio sintetizado: {len(raw_audio)} bytes")
    
    # 2. Convertir a WAV 16kHz mono con ffmpeg
    cmd = [
        "ffmpeg", "-y", "-i", "pipe:0",
        "-f", "wav", "-ar", "16000", "-ac", "1",
        "pipe:1"
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wav_bytes, err = proc.communicate(input=raw_audio)
    print(f"WAV convertido: {len(wav_bytes)} bytes (exit code: {proc.returncode})")
    
    # 3. Transcribir con Gemini
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
    prompt = "Escuchá atentamente este audio y transcribí de forma exacta qué dice en español. Devolvé únicamente el texto hablado, sin comillas ni aclaraciones."
    
    res = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=[part, prompt],
        config=types.GenerateContentConfig(max_output_tokens=100)
    )
    print(f"Transcripción de Gemini: '{res.text.strip()}'")

asyncio.run(test())
