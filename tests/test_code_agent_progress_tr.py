"""Türkçe kod ajanı paneli, canlı süre ve gerçek model raporlama testleri."""
from pathlib import Path
from unittest import TestCase, mock

from actions import dev_agent
from core import coding_router, jarvis_agent, nvidia_account


class CodeAgentModelReportTests(TestCase):
    def tearDown(self):
        # İş geçmişinin diğer birim testlerine sızmasını önle.
        with dev_agent._state_lock:
            dev_agent._JOB = {}
        dev_agent._player_ref = None

    def _start(self):
        dev_agent._new_job(Path("simple_calculator"), "kodlama modeli",
                           "Python hesap makinesi oluştur", None, kind="build")

    def test_successful_nvidia_model_is_reported(self):
        self._start()
        with mock.patch.object(coding_router, "ladder",
                               return_value=[jarvis_agent.PROVIDER_ID, ""]), \
             mock.patch.object(nvidia_account, "api_key",
                               return_value="private-test-key"), \
             mock.patch.object(nvidia_account, "available_models",
                               return_value=["nvidia/nemotron-3.5-lightning-30b-a3b"]), \
             mock.patch.object(nvidia_account, "complete_text",
                               return_value='{"stages":[]}'):
            output = dev_agent._get_model().generate_content("planla")
        self.assertIn("stages", output.text)
        job = dev_agent._job_snapshot()
        self.assertEqual(job["model_used"],
                         "NVIDIA · nvidia/nemotron-3.5-lightning-30b-a3b")
        self.assertEqual(job["model_attempt"], job["model_used"])
        self.assertTrue(any("Model yanıt verdi:" in message for _, message in job["steps"]))
        self.assertNotIn("private-test-key", repr(job))

    def test_fallback_reports_model_that_actually_responded(self):
        self._start()
        models = ["nvidia/nemotron-3.5-lightning-30b-a3b",
                  "nvidia/nemotron-3.5-super-vl-120b-a12b"]
        def complete(_prompt, *, model):
            if model == models[0]:
                raise RuntimeError("NVIDIA 504: Sunucu zaman aşımı")
            return "İkinci model yanıtı"

        with mock.patch.object(coding_router, "ladder",
                               return_value=[jarvis_agent.PROVIDER_ID, ""]), \
             mock.patch.object(nvidia_account, "api_key", return_value="key"), \
             mock.patch.object(nvidia_account, "available_models", return_value=models), \
             mock.patch.object(nvidia_account, "complete_text", side_effect=complete):
            output = dev_agent._get_model().generate_content("planla")
        self.assertEqual(output.text, "İkinci model yanıtı")
        self.assertEqual(dev_agent._job_snapshot()["model_used"],
                         "NVIDIA · nvidia/nemotron-3.5-super-vl-120b-a12b")

    def test_only_attempt_is_reported_without_success(self):
        self._start()
        with mock.patch.object(coding_router, "ladder",
                               return_value=[jarvis_agent.PROVIDER_ID]), \
             mock.patch.object(nvidia_account, "api_key", return_value="key"), \
             mock.patch.object(nvidia_account, "available_models",
                               return_value=["nvidia/nemotron-3.5-lightning-30b-a3b"]), \
             mock.patch.object(nvidia_account, "complete_text",
                               side_effect=RuntimeError("NVIDIA 401: Anahtar geçersiz")):
            with self.assertRaises(RuntimeError):
                dev_agent._get_model().generate_content("planla")
        job = dev_agent._job_snapshot()
        self.assertNotIn("model_used", job)
        self.assertIn("NVIDIA", job["model_attempt"])


class CodeAgentUiTurkishTests(TestCase):
    def test_code_agent_ui_is_turkish_and_clock_is_live(self):
        text = (Path(__file__).resolve().parents[1] / "gui/window.py").read_text(
            encoding="utf-8")
        for phrase in ("KOD AJANI —", "PLANLAMA", "İSTEK", "DOSYALAR",
                       "İŞLEMLER — en yeni üstte", "DENENEN MODEL",
                       "YANIT VEREN MODEL", "_refresh_code_job_clock",
                       "self._code_job_clock.start()"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn("STEPS — newest first</div>", text)

    def test_stage_progress_is_in_turkish(self):
        text = (Path(__file__).resolve().parents[1] / "actions/dev_agent.py").read_text(
            encoding="utf-8")
        self.assertIn("Proje aşamalar halinde planlanıyor", text)
        self.assertIn("Model yanıt verdi: NVIDIA", text)
        self.assertNotIn('"Planning the project in stages…" ', text)
