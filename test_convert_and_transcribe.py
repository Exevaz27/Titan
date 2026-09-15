
import subprocess, os, asyncio
from dotenv import load_dotenv
load_dotenv('/home/exevaz27/titan/.env')
from audio.tts import tts
from google import genai
from google.genai import types

async def main():
    print('Synthesizing audio...', flush=True)
    audio = await tts.synthesize_to_bytes('Hola Titán, ¿cuándo juega Boca?')
    print(f'Synthesized: {len(audio)} bytes', flush=True)
    
    cmd = ['ffmpeg', '-y', '-i', 'pipe:0', '-f', 'wav', '-ar', '16000', '-ac', '1', 'pipe:1']
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wav_bytes, _ = proc.communicate(input=audio)
    print(f'Converted to WAV: {len(wav_bytes)} bytes', flush=True)
    
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    part = types.Part.from_bytes(data=wav_bytes, mime_type='audio/wav')
    prompt = 'Transcribí exactamente qué dice el usuario en este audio en español. Devolvé solo la transcripción en una sola línea.'
    
    res = client.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=[part, prompt],
        config=types.GenerateContentConfig(max_output_tokens=60)
    )
    print('Gemini Transcription:', repr(res.text.strip()), flush=True)

asyncio.run(main())
