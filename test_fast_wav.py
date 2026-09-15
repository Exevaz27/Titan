
import os, sys, asyncio, subprocess, io, wave
from dotenv import load_dotenv
load_dotenv('/home/exevaz27/titan/.env')
from google import genai
from google.genai import types

buf = io.BytesIO()
with wave.open(buf, 'wb') as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)
    wf.writeframes(b'\x00\x00' * 16000)
wav_bytes = buf.getvalue()

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
part = types.Part.from_bytes(data=wav_bytes, mime_type='audio/wav')
print('Sending to Gemini...', flush=True)
try:
    res = client.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=[part, 'Transcribe exact text or describe audio'],
        config=types.GenerateContentConfig(max_output_tokens=50)
    )
    print('Gemini replied:', res.text, flush=True)
except Exception as e:
    print('Gemini error:', e, flush=True)
