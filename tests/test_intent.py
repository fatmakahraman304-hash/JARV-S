"""Task, question or chat? — the safety net under the voice model's tool calls."""
import unittest
from unittest.mock import patch

from core import intent

CASES = {
    "Blender'ı yükledin mi?": "status", "Blender'ı yükledin mi": "status", "bitti mi?": "status", "ne durumda?": "status",
    "is it done?": "status",
    "Blender'ı kur": "task", "duvar yap": "task", "Blender'da ahşap bir masa yap": "task", "onu iki kat büyüt": "task",
    "şunu kırmızı yap": "task", "geri al": "task", "make it red": "task",
    "Blender'da bevel nasıl yapılır?": "how", "geometri düğümleri nedir?": "how", "how do I add a light?": "how",
    "ileride ev istesem nasıl yapacak acaba": "hypothetical", "şimdi jarvis duvar yap desem yapar": "hypothetical",
    "apartman yapabilir mi?": "hypothetical",
    "beğenmedim": "feedback", "olmamış": "feedback", "güzel olmuş": "feedback",
    "Blender'da masa yapar mısın?": "task", "Blender'ı kurabilir misin?": "task", "lütfen pencere ekle": "task",
    "can you make a chair?": "task", "Blender'ı kurdun mu?": "status",
    "merhaba": "chat", "teşekkürler": "chat", "nasılsın?": "chat", "tamam": "chat",
}


class Kinds(unittest.TestCase):
    def test_kinds(self):
        wrong = {t: intent.kind(t) for t, want in CASES.items() if intent.kind(t) != want}
        self.assertEqual(wrong, {})

    def test_feedback_with_an_instruction_acts(self):
        self.assertTrue(intent.should_act("beğenmedim, ayakları kalınlaştır"))
        self.assertFalse(intent.should_act("Blender'ı yükledin mi?"))


class BlenderGuard(unittest.TestCase):
    def test_question_does_not_install_or_build(self):
        from plugins import blender_studio as studio
        with patch.object(studio, "process") as proc, patch.object(studio, "executable", return_value="blender"):
            out = studio.run({"action": "install", "request": "Blender'ı yükledin mi?"})
            out2 = studio.run({"action": "new", "request": "ileride apartman istesem yapabilir mi?"})
        proc.assert_not_called()
        self.assertIn("NOT EXECUTED", out)
        self.assertIn("hypothetical", out2)

    def test_command_still_runs(self):
        from plugins import blender_studio as studio
        with patch.object(studio, "process", return_value="Hazır.") as proc, patch.object(studio, "executable", return_value="blender"):
            studio.run({"action": "lessons", "request": ""})
            studio.run({"action": "teach", "request": "Ürün çekiminde 85 mm lens kullan"})
        self.assertTrue(proc.called)


class HologramGuard(unittest.TestCase):
    def test_question_does_not_model(self):
        from plugins import hologram
        player = type("P", (), {"show_hologram": lambda self, c: (_ for _ in ()).throw(AssertionError("acted"))})()
        self.assertIn("NOT EXECUTED", hologram.run({"action": "make", "request": "ileride araba istesem yapar mı?"}, player))


if __name__ == "__main__":
    unittest.main()
