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


class EveryTool(unittest.TestCase):
    def test_changing_tools_are_guarded_for_questions(self):
        for name, args in (("open_app", {"app": "spotify"}), ("todo_list", {"action": "add", "task": "süt"}),
                           ("send_message", {"to": "anne"}), ("file_manager", {"action": "delete"})):
            self.assertIn("NOT EXECUTED", intent.guard(name, args, "ileride Spotify'ı açsam ne olur?"), name)
            self.assertIn("NOT EXECUTED", intent.guard(name, args, "mesajı gönderdin mi?"), name)
            self.assertEqual(intent.guard(name, args, "Spotify'ı aç"), "", name)
            self.assertEqual(intent.guard(name, args, "tamam"), "", name)          # confirmations go through

    def test_looking_tools_answer_questions(self):
        for name, args in (("weather_report", {}), ("recall_memory", {"query": "x"}), ("todo_list", {"action": "list"}),
                           ("blender_studio", {"action": "status"}), ("system_status", {})):
            self.assertEqual(intent.guard(name, args, "bitti mi?"), "", name)

    def test_main_uses_the_guard_for_every_tool(self):
        src = open(__import__("pathlib").Path(__file__).resolve().parent.parent / "main.py", encoding="utf-8").read()
        self.assertIn("blocked = self._intent_guard(name, args)", src)


class WorkStatus(unittest.TestCase):
    def test_reports_real_outcomes_and_running_jobs(self):
        from core import activity
        from plugins import work_status
        activity.record("files", "Dosya taşındı: rapor.pdf", "ok")
        activity.record("web", "Yapılamadı: Web araması", "fail")
        out = work_status.run({})
        self.assertIn("Dosya taşındı: rapor.pdf (tamam)", out)
        self.assertIn("BAŞARISIZ", out)
        self.assertIn("Blender:", out)
        self.assertTrue(intent.is_read_only("work_status", {}))


class HologramGuard(unittest.TestCase):
    def test_question_does_not_model(self):
        from plugins import hologram
        player = type("P", (), {"show_hologram": lambda self, c: (_ for _ in ()).throw(AssertionError("acted"))})()
        self.assertIn("NOT EXECUTED", hologram.run({"action": "make", "request": "ileride araba istesem yapar mı?"}, player))


if __name__ == "__main__":
    unittest.main()
