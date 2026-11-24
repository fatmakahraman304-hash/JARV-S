import unittest
from core import integrated_capabilities as integrated
from core import thinking_studio as studio
from core.core_modes import route
from plugins import thinking_studio as plugin


class IntegratedCapabilitiesTests(unittest.TestCase):
    def test_every_catalog_item_is_indexed_and_retrievable(self):
        rows, _ = integrated.catalog()
        self.assertEqual(set(rows),set(range(1,1001)))
        for n in rows:
            with self.subTest(n=n):
                self.assertEqual(integrated.resolve(str(n)),(n,))
                self.assertIn(studio.FEATURES[n][0],integrated.guidance((n,)))

    def test_natural_requests(self):
        examples = {
            "Bana beş soru sor":145,
            "Tarifi iki katına çıkar":578,
            "Ortak harcama hesabı yap":619,
            "Ortalama medyan hesapla":804,
            "İki belge arasındaki fark nedir":932,
            "Zar at":757,
            "Takvim çakışma kontrolü":907,
            "Neden ışık hızı?":676,
        }
        for text,n in examples.items():
            with self.subTest(text=text):
                self.assertIn(n,integrated.resolve(text,route(text)))

    def test_no_activation_required(self):
        studio.activate((0,))
        self.assertIsNone(studio.control_command("mod 145"))
        self.assertIsNone(studio.control_command("mini sınav"))
        self.assertIsNone(studio.control_command("zar at"))
        self.assertEqual(studio.control_command("normal moda dön"),(0,))
        self.assertEqual(integrated.resolve("mod 145"),(145,))
        self.assertIn("Mini sınav",plugin.run({"action":"resolve","query":"quiz yap"}))
        self.assertEqual(studio.active(),())
        self.assertEqual(integrated.resolve("merhaba"),())
        self.assertEqual(integrated.resolve("[SYSTEM_ALERT] mini sınav"),())
        self.assertEqual(integrated.resolve("9"*5000),())

    def test_followups_and_reset(self):
        history=[{"role":"user","content":"tarifi iki katına çıkar"},
                 {"role":"tool","content":"rastgele"},
                 {"role":"user","content":"daha kısa yap"}]
        self.assertIn(578,integrated.history_features(history,(19,)))
        history.append({"role":"user","content":"merhaba"})
        self.assertEqual(integrated.history_features(history),())

    def test_pipeline_automatic_and_cached(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from providers.engine_pipeline import PipelineEngine
        history=[{"role":"user","content":"istatistik hesapla"}]
        fake=SimpleNamespace(_system=studio.system_block(),_history=history,
                             _trimmed=lambda:history.copy(),tool_names=lambda:["studio_utilities"])
        with patch("core.integrated_capabilities.history_features",wraps=integrated.history_features) as lookup:
            msgs=PipelineEngine._messages(fake)
            self.assertIn("804. Özet istatistik",msgs[0]["content"])
            self.assertIn("studio_utilities",msgs[0]["content"])
            self.assertEqual(msgs[1:],history)
            history.append({"role":"tool","content":"hesap sonucu"})
            PipelineEngine._messages(fake)
            self.assertEqual(lookup.call_count,1)
            history.append({"role":"user","content":"zar at"})
            msgs=PipelineEngine._messages(fake)
            self.assertIn("757. Zar ve kart sistemi",msgs[0]["content"])
            self.assertNotIn("804. Özet istatistik",msgs[0]["content"])
            self.assertEqual(lookup.call_count,2)
            self.assertEqual(studio.active(),())

    def test_app_requirements_not_false_claims(self):
        text=integrated.guidance((481,491,496))
        self.assertIn("otomatik kaynak yakalama yok",text)
        self.assertIn("otomatik sohbet izolasyonu yok",text)
        self.assertIn("tam sistem yedeği değil",text)
