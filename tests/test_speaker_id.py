"""Tests de la huella de voz (2026-09-17, multi-voz 2026-09-18): lógica pura, sin satélite."""

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audio import speaker_id as huella


def _rand_vec(dim, seed):
    import random
    rnd = random.Random(seed)
    v = [rnd.gauss(0, 1) for _ in range(dim)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _noisy(base, seed, sigma=0.05):
    import random
    rnd = random.Random(seed)
    s = [x + rnd.gauss(0, sigma) for x in base]
    n = math.sqrt(sum(x * x for x in s))
    return [x / n for x in s]


class TestCosine(unittest.TestCase):
    def test_identicos_da_1(self):
        v = _rand_vec(256, 1)
        self.assertAlmostEqual(huella.cosine(v, v), 1.0, places=6)

    def test_ortogonales_da_0(self):
        a = [1.0] + [0.0] * 255
        b = [0.0, 1.0] + [0.0] * 254
        self.assertAlmostEqual(huella.cosine(a, b), 0.0, places=6)


class TestMultiVoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_dir = huella.VOICEPRINT_DIR
        huella.VOICEPRINT_DIR = self.tmp

    def tearDown(self):
        huella.VOICEPRINT_DIR = self.orig_dir
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dos_voces_se_distinguen(self):
        base_a = _rand_vec(256, 10)
        base_b = _rand_vec(256, 77)
        huella.save_voiceprint([_noisy(base_a, 11 + i) for i in range(8)],
                               name="exequiel", display="Exequiel")
        huella.save_voiceprint([_noisy(base_b, 31 + i) for i in range(8)],
                               name="oriana", display="Oriana")
        self.assertEqual(huella.list_voiceprints(), ["exequiel", "oriana"])

        ident_a, score_a = huella.match_embedding(_noisy(base_a, 99))
        self.assertEqual(ident_a, "exequiel")
        self.assertGreater(score_a, huella.SIMILARITY_THRESHOLD)

        ident_b, score_b = huella.match_embedding(_noisy(base_b, 100))
        self.assertEqual(ident_b, "oriana")
        self.assertGreater(score_b, huella.SIMILARITY_THRESHOLD)

        ident_x, score_x = huella.match_embedding(_rand_vec(256, 555))
        self.assertEqual(ident_x, "desconocido")
        self.assertLess(score_x, huella.SIMILARITY_THRESHOLD)

    def test_display_y_safe_name(self):
        huella.save_voiceprint([_rand_vec(64, 3)], name="oriana", display="Oriana")
        self.assertEqual(huella.display_name("oriana"), "Oriana")
        self.assertEqual(huella._safe_name("Oriana Pérez"), "orianaperez")
        self.assertEqual(huella._safe_name("Exequiel"), "exequiel")

    def test_sin_huellas_da_desconocido(self):
        ident, _ = huella.match_embedding(_rand_vec(256, 5))
        self.assertEqual(ident, "desconocido")
        self.assertEqual(huella.list_voiceprints(), [])

    def test_delete_una_no_afecta_otra(self):
        huella.save_voiceprint([_rand_vec(64, 3)], name="exequiel")
        huella.save_voiceprint([_rand_vec(64, 4)], name="oriana")
        self.assertTrue(huella.delete_voiceprint("oriana"))
        self.assertFalse(huella.has_voiceprint("oriana"))
        self.assertTrue(huella.has_voiceprint("exequiel"))

    def test_identity_prompt_tag(self):
        self.assertEqual(huella.identity_prompt_tag(), "")  # sin huellas
        huella.save_voiceprint([_rand_vec(64, 3)], name="oriana", display="Oriana")
        huella._last_identity = {"identity": "oriana", "score": 0.9, "time": 1e12}
        tag = huella.identity_prompt_tag()
        self.assertIn("Oriana", tag)

    def test_enrollment_phrases(self):
        self.assertEqual(len(huella.ENROLL_PHRASES), 8)


class TestEnrollmentState(unittest.TestCase):
    def test_start_cancel(self):
        msg = huella.start_enrollment()  # sin satélite: aviso, no activa
        self.assertFalse(huella.enrollment_active())
        self.assertIn("Windows", msg)
        huella._enrollment.update({"active": True, "idx": 0, "embeddings": [],
                                   "name": "oriana", "display": "Oriana"})
        self.assertTrue(huella.enrollment_active())
        msg2 = huella.cancel_enrollment()
        self.assertFalse(huella.enrollment_active())
        self.assertIn("cancel", msg2.lower())


class TestEnrollmentEchoGate(unittest.TestCase):
    """Anti-eco por timing (2026-09-18): el audio captado mientras Titán
    habla (o <1.5s después) se ignora sin llegar al STT ni al embedding."""

    def _stub_tts(self, is_speaking, last_speech_time):
        import types
        from types import SimpleNamespace
        mod = types.ModuleType("audio.tts")
        mod.tts = SimpleNamespace(_is_speaking=is_speaking,
                                  last_speech_time=last_speech_time)
        self._prev = sys.modules.get("audio.tts")
        sys.modules["audio.tts"] = mod

    def tearDown(self):
        if getattr(self, "_prev", None) is None:
            sys.modules.pop("audio.tts", None)
        else:
            sys.modules["audio.tts"] = self._prev
        huella._enrollment.update({"active": False, "idx": 0,
                                   "embeddings": [], "name": None,
                                   "display": None})

    def test_ignora_audio_mientras_titan_habla(self):
        self._stub_tts(is_speaking=True, last_speech_time=0)
        huella._enrollment.update({"active": True, "idx": 0,
                                   "embeddings": [], "name": "exequiel",
                                   "display": "Exequiel"})
        self.assertIsNone(huella.handle_enrollment_audio(b"\x00" * 3200,
                                                         16000, None))

    def test_ignora_audio_justo_despues_de_hablar(self):
        import time
        self._stub_tts(is_speaking=False,
                       last_speech_time=time.time() - 0.5)
        huella._enrollment.update({"active": True, "idx": 0,
                                   "embeddings": [], "name": "exequiel",
                                   "display": "Exequiel"})
        self.assertIsNone(huella.handle_enrollment_audio(b"\x00" * 3200,
                                                         16000, None))

    def test_procesa_audio_si_titan_no_habla(self):
        # 0.1s de silencio pasa el gate (Titán no habla) y llega al chequeo
        # de duración -> pide repetir la frase, sin tragar el registro.
        self._stub_tts(is_speaking=False, last_speech_time=0)
        huella._enrollment.update({"active": True, "idx": 0,
                                   "embeddings": [], "name": "exequiel",
                                   "display": "Exequiel"})
        r = huella.handle_enrollment_audio(b"\x00" * 3200, 16000, None)
        self.assertIn("repetí la frase", r)
        self.assertTrue(huella.enrollment_active())  # sigue en registro


if __name__ == "__main__":
    unittest.main()
