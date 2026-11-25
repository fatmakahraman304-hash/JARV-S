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

    def test_multiple_independent_requests_and_index(self):
        ids=integrated.resolve("Kodlarımı incele; ayrıca bütçemi hesapla; bir de zar at",limit=4)
        self.assertEqual(ids[:3],(274,612,757))
        self.assertLessEqual(len(ids),4)
        self.assertEqual(integrated.resolve("code review and also monthly budget")[:2],(274,612))
        self.assertEqual(integrated.resolve("mod 145 ve 578"),(145,578))
        rows,_=integrated.catalog()
        with self.assertRaises(TypeError):
            rows[1]=None
        self.assertIn(274,integrated.candidates("kodlarimi incele",integrated._roots("kodlarimi incele")))
        self.assertEqual(integrated.resolve("merhaba"),())

    def test_utility_bindings_are_real_operations(self):
        from core.studio_utilities import OPERATIONS
        for n,op in studio.UTILITY_BINDINGS.items():
            with self.subTest(n=n):
                self.assertIn(op,OPERATIONS)
                self.assertIn("studio_utilities/"+op,studio.workflow_for(n))
        self.assertIn("data_quality",integrated.guidance((801,)))
        self.assertIn("trend",integrated.guidance((813,)))

    def test_instruction_budget_does_not_cut_boundaries(self):
        from unittest.mock import patch
        with patch.object(studio,"workflow_for",return_value="x"*400+" Sınır."):
            self.assertEqual(integrated.guidance((578,),max_chars=150),"")
        self.assertEqual(integrated.resolve("[SYSTEM_ALERT] mini sınav; zar at"),())

    def test_numeric_and_short_reply_context(self):
        history=[{"role":"user","content":"tarifi iki katına çıkar"},
                 {"role":"assistant","content":"Kaç kişi için?"},
                 {"role":"user","content":"6"}]
        self.assertIn(578,integrated.history_features(history,(19,)))
        history.append({"role":"user","content":"8 kişi için"})
        self.assertIn(578,integrated.history_features(history))
        history.append({"role":"user","content":"sadece sonucu ver"})
        self.assertIn(578,integrated.history_features(history))
        history.append({"role":"user","content":"mod 145"})
        self.assertEqual(integrated.history_features(history),(145,))
        self.assertEqual(integrated.history_features([{"role":"user","content":"145"}]),())
        self.assertEqual(integrated.resolve("145"),(145,))

    def test_context_does_not_cross_image_only_turn(self):
        history=[{"role":"user","content":"mini sınav"},
                 {"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,AAAA"}}]},
                 {"role":"user","content":"daha ayrıntılı"}]
        self.assertEqual(integrated.history_features(history),())

    def test_pipeline_core_and_capability_guidance_agree_on_short_answers(self):
        from types import SimpleNamespace
        from providers.engine_pipeline import PipelineEngine
        history = [{"role": "user", "content": "Tarifi iki katına çıkar"},
                   {"role": "assistant", "content": "Kaç kişi için?"},
                   {"role": "user", "content": "6"}]
        fake = SimpleNamespace(_system=studio.system_block(), _history=history,
                               _trimmed=lambda: history.copy(), tool_names=lambda: ["studio_utilities"])
        messages = PipelineEngine._messages(fake)
        self.assertIn("Ana: Yemek", messages[0]["content"])
        self.assertIn("578.", messages[0]["content"])
        self.assertEqual(messages[1:], history)
        history.extend([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]},
                        {"role": "user", "content": "devam et"}])
        messages = PipelineEngine._messages(fake)
        self.assertNotIn("Ana: Yemek", messages[0]["content"])
        self.assertNotIn("578.", messages[0]["content"])

    def test_guidance_tool_availability_and_total_budget(self):
        text=integrated.guidance((578,),available_tools=())
        self.assertIn("bu oturumda",text.lower())
        self.assertIn("çalıştırılmış hesap iddia etme",text)
        self.assertNotIn("sunulmuyor",integrated.guidance((578,),available_tools=("studio_utilities",)))
        self.assertLessEqual(len(integrated.guidance((578,804,907),max_chars=650)),650)
