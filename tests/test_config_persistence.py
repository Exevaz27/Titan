import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from brain.gemini_client import GeminiBrain
except ImportError:
    GeminiBrain = None


@unittest.skipUnless(GeminiBrain, "Requiere google-genai")
class TestConfigPersistence(unittest.TestCase):
    def test_update_api_key_preserves_existing_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "TELEGRAM_BOT_TOKEN=keep-me\n"
                "TITAN_API_TOKEN=keep-this-too\n"
                "GEMINI_API_KEY=old-key\n",
                encoding="utf-8",
            )
            brain = object.__new__(GeminiBrain)
            brain.client = None
            fake_config = type("Config", (), {
                "base_dir": Path(temp_dir),
                "gemini_api_key": "",
                "gemini_model": "test-model",
            })()
            with patch("brain.gemini_client.config", fake_config), patch.object(brain, "_init_client"):
                brain.update_api_key("new-key-that-is-not-logged")

            content = env_path.read_text(encoding="utf-8")
            self.assertIn("TELEGRAM_BOT_TOKEN=keep-me", content)
            self.assertIn("TITAN_API_TOKEN=keep-this-too", content)
            self.assertIn("GEMINI_API_KEY=new-key-that-is-not-logged", content)
            self.assertNotIn("GEMINI_API_KEY=old-key", content)

    def test_update_api_key_rejects_empty_value(self):
        brain = object.__new__(GeminiBrain)
        with self.assertRaises(ValueError):
            brain.update_api_key("  ")


if __name__ == "__main__":
    unittest.main()