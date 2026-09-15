
import subprocess, os, asyncio, tempfile
from dotenv import load_dotenv
load_dotenv('/home/exevaz27/titan/.env')
from audio.tts import tts
from google import genai
from google.genai import types

async def main():
    audio = await tts.synthesize_to_bytes('Hola Titán, ¿cuándo juega Boca?')
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        wav_path = f.name
    
    cmd = ['ffmpeg', '-y', '-i', 'pipe:0', '-ar', '16000', '-ac', '1', wav_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.communicate(input=audio)
    
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    print('Uploading WAV file to Gemini Files API...', flush=True)
    uploaded = client.files.upload(file=wav_path)
    print('Uploaded:', uploaded.name, flush=True)
    
    try:
        res = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=[uploaded, 'Transcribí exactamente qué dice el usuario en este audio en español.']
        )
        print('SUCCESS:', res.text, flush=True)
    except Exception as e:
        print('ERROR:', e, flush=True)
    finally:
        client.files.delete(name=uploaded.name)
        os.remove(wav_path)

asyncio.run(main())
