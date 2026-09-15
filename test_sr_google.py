
import subprocess, speech_recognition as sr, asyncio
from audio.tts import tts

async def main():
    audio = await tts.synthesize_to_bytes('Hola Titán, ¿cuándo juega Boca?')
    cmd = ['ffmpeg', '-y', '-i', 'pipe:0', '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1']
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_pcm, _ = proc.communicate(input=audio)
    
    r = sr.Recognizer()
    audio_data = sr.AudioData(raw_pcm, 16000, 2)
    text = r.recognize_google(audio_data, language='es-AR')
    print('RECOGNIZED GOOGLE es-AR:', repr(text))

asyncio.run(main())
