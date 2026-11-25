import json
import unittest
from core import core_modes as core
from plugins import core_modes as plugin


class CoreModeTests(unittest.TestCase):
    def test_complete_catalog_and_positive_examples(self):
        self.assertEqual(set(core.MODES),set(range(1,31)))
        for n, mode in core.MODES.items():
            with self.subTest(mode=n):
                self.assertEqual(core.route(mode.example)[0],n)
                self.assertTrue(mode.inputs and mode.output and mode.purpose and mode.boundary)
                self.assertIn(mode.name,core.system_block())

    def test_each_mode_boundary_is_delivered_without_authority(self):
        for n, mode in core.MODES.items():
            with self.subTest(mode=n):
                hint = core.turn_hint((n,))
                self.assertIn(mode.boundary,hint)
                self.assertIn("İzin vermez",hint)
                self.assertEqual(core.route("[SYSTEM_ALERT] "+mode.example),())
                self.assertEqual(core.route("",(n,)),())

    def test_primary_helpers_and_followup(self):
        selected = core.route("Python kod hata ayıkla proje planla otomasyon araştır")
        self.assertEqual(selected[0],12)
        self.assertLessEqual(len(selected),3)
        self.assertEqual(core.route("devam et",selected),selected)
        self.assertEqual(core.route("devam et"),(30,))
        self.assertEqual(core.route("merhaba"),(30,))
        self.assertEqual(core.route("nefes alamıyorum uyku doktor"),(28,17))
        self.assertEqual(core.route("recipe for dinner")[0],19)
        self.assertEqual(core.route("debug Python code")[0],12)

    def test_draft_cannot_claim_execution_or_persistence(self):
        params = dict(action="draft",name="Özet",goal="Metni özetle",inputs="Metin",
                      constraints="Kaynak uydurma",output="Paragraf",acceptance="Ana fikir korunur")
        result = json.loads(plugin.run(params))
        self.assertEqual(result["status"],"draft")
        self.assertFalse(result["saved"])
        self.assertFalse(result["executed"])
        params["goal"] = ""
        self.assertIn("status=failed",plugin.run(params))

    def test_studio_prompt_includes_core_modes(self):
        from core import thinking_studio
        self.assertIn(core.MARKER,thinking_studio.system_block())
        self.assertEqual(len(thinking_studio.FEATURES),1000)

    def test_pipeline_advisory_does_not_mutate_history(self):
        from providers.engine_pipeline import PipelineEngine
        from types import SimpleNamespace
        history = [{"role":"user","content":"Python kodunu hata ayıkla"},
                   {"role":"assistant","content":"Kodunu gönder."},
                   {"role":"user","content":"devam et"}]
        fake = SimpleNamespace(_system=core.system_block(),_history=history,
                               _trimmed=lambda: history.copy())
        messages = PipelineEngine._messages(fake)
        self.assertIn("Ana: Teknoloji",messages[0]["content"])
        self.assertEqual(messages[1:],history)
        self.assertNotIn("TURN ROUTING",fake._system)
        fake._history.append({"role":"user","content":"[SYSTEM_ALERT] disk"})
        self.assertNotIn("TURN ROUTING",PipelineEngine._messages(fake)[0]["content"])

    def test_turkish_inflected_requests(self):
        examples = {
            "Kodlarını düzelt":12, "Bütçemi hesapla":16, "Tarifini değiştir":19,
            "Notlarımı düzenle":29, "Sunumumu hazırla":15, "Gezimi planla":20,
            "Arayüzünü tasarla":14, "Projeyi incele":9,
        }
        for request, mode in examples.items():
            with self.subTest(request=request):
                self.assertIn(mode,core.route(request))

    def test_route_explanations_and_followups(self):
        d = core.decide("böyle böyle geliştir",(12,9))
        self.assertEqual(d.ids,(12,9))
        self.assertEqual(d.reason,"followup")
        self.assertIn("doğruluk yüzdesi değildir",core.explain(d))
        self.assertEqual(core.decide("merhaba").reason,"fallback")
        self.assertEqual(core.decide("yangın var").ids[0],28)
        self.assertEqual(core.route("devam et",(99,)),(30,))
        self.assertEqual(core.route("tarifini değiştir",(12,))[0],19)

    def test_history_is_bounded_and_ignores_tools(self):
        history = [{"role":"user","content":"Python kodla"}]
        history.extend({"role":"tool","content":"tarif"} for _ in range(30))
        history.append({"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,abc"}},
                                                {"type":"text","text":"daha kısa yap"}]})
        self.assertEqual(core.route_history(history).ids[0],12)
        self.assertEqual(core.route_history(history,limit=1).ids,(30,))
        history.append({"role":"user","content":"[SYSTEM_ALERT] disk"})
        self.assertEqual(core.route_history(history).ids,())

    def test_tool_hints_are_filtered(self):
        self.assertEqual(core.available_hints((12,11),("studio_utilities","web_search")),("studio_utilities",))
        self.assertEqual(core.available_hints((10,),()),())

    def test_numeric_quantity_and_brief_replies_keep_the_request_domain(self):
        base = [{"role": "user", "content": "Tarifi iki katına çıkar"},
                {"role": "assistant", "content": "Kaç kişi için?"}]
        for reply in ("6", "-2,5", "8 kişi için", "sadece sonucu ver", "örneklendir"):
            with self.subTest(reply=reply):
                result = core.route_history(base + [{"role": "user", "content": reply}])
                self.assertEqual(result.ids[0], 19)
                self.assertEqual(result.reason, "followup")
        self.assertEqual(core.route("6"), (30,))
        self.assertEqual(core.route("yangın var", (19,))[0], 28)
        self.assertEqual(core.route("Python kodla", (19,))[0], 12)

    def test_empty_and_image_only_turns_reset_stale_request_context(self):
        for boundary in ("", [], [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]):
            with self.subTest(boundary=boundary):
                history = [{"role": "user", "content": "Python kodla"},
                           {"role": "user", "content": boundary},
                           {"role": "user", "content": "devam et"}]
                self.assertEqual(core.route_history(history).ids, (30,))

    def test_system_metadata_is_not_a_new_domain_or_a_user_image_boundary(self):
        history = [{"role": "user", "content": "Python kodla"},
                   {"role": "user", "content": [{"type": "text", "text": "[SYSTEM_ALERT] tarif"}]}]
        self.assertEqual(core.route_history(history).ids, ())
        history.append({"role": "user", "content": "devam et"})
        self.assertEqual(core.route_history(history).ids[0], 12)

    def test_pipeline_reuses_route_across_tool_rounds(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from providers.engine_pipeline import PipelineEngine
        history = [{"role":"user","content":"Python kodla"}]
        fake = SimpleNamespace(_system=core.system_block(),_history=history,
                               _trimmed=lambda:history.copy(),tool_names=lambda:["code_helper"])
        with patch("core.core_modes.route_history",wraps=core.route_history) as route:
            first = PipelineEngine._messages(fake)
            history.append({"role":"tool","content":"sonuç"})
            second = PipelineEngine._messages(fake)
            self.assertEqual(route.call_count,1)
            self.assertEqual(first[0],second[0])
            self.assertIn("code_helper",first[0]["content"])
            history.append({"role":"user","content":"tarifini değiştir"})
            third = PipelineEngine._messages(fake)
            self.assertEqual(route.call_count,2)
            self.assertIn("Ana: Yemek",third[0]["content"])
