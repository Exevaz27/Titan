import asyncio
import os
import unittest
from pathlib import Path
import sys

# Añadir directorio raíz al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio.tts import tts
from core.config import config

class TestTTS(unittest.IsolatedAsyncioTestCase):
    async def test_edge_tts_synthesis(self):
        """Verifica que Edge-TTS pueda generar audio en español argentino sin errores"""
        import tempfile
        import edge_tts

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            temp_path = tmp.name

        try:
            communicate = edge_tts.Communicate(
                text="Che, esto es una prueba técnica del motor de síntesis de voz.",
                voice=config.tts_voice,
                rate=config.tts_rate,
                pitch=config.tts_pitch
            )
            await communicate.save(temp_path)
            self.assertTrue(os.path.exists(temp_path))
            self.assertGreater(os.path.getsize(temp_path), 1000)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
