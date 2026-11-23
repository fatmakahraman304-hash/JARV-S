"""Offline regressions: all live public lookups and search modes use fresh sources.

No provider keys, external requests, or billable model calls in these tests.
"""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from core.live_facts import needs_live_lookup, lookup_live_evidence
from actions import web_search as web


class LivePublicSearchTests(unittest.TestCase):
    def test_current_public_questions_trigger_live_lookup(self):
        for text in (
            "Fenerbahçe'nin sıradaki maçı ne zaman?",
            "Bugün İstanbul'da hava durumu nasıl?",
            "Bitcoin kaç TL?",
            "Dolar kuru ne kadar?",
            "En son yapay zekâ haberleri neler?",
            "Şu an borsa nasıl?",
            "Tesla CEO'su kim?",
            "İnternetten en iyi 3D yazıcıları araştır",
            "Webden uçuş saatlerini bul",
            "What is the latest news today?",
            "When is the next game?",
            "Deprem oldu mu bugün?",
            "Yeni telefon fiyatları ne kadar?",
        ):
            with self.subTest(text=text):
                self.assertTrue(needs_live_lookup(text))

    def test_local_commands_and_static_history_stay_fast(self):
        for text in (
            "Merhaba AETHER",
            "Chrome'u aç",
            "Sesi yükselt",
            "Fenerbahçe nasıl kuruldu?",
            "Bana bir hikâye yaz",
            "Projemin kodunu düzelt",
            "Güncel kodumu kontrol et",
            "Bilgisayarımı şimdi kapat",
            "Bugün çok mutluyum",
        ):
            with self.subTest(text=text):
                self.assertFalse(needs_live_lookup(text))

    def test_results_include_retrieval_time_sources_and_no_false_freshness(self):
        now = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)
        queries = []

        def search(query, max_results=7):
            queries.append((query, max_results))
            return [
                {"title": "Price announced today",
                 "snippet": "Test stock price (example only)",
                 "url": "https://example.org/current",
                 "date": "2026-11-23"},
                {"title": "duplicate", "snippet": "duplicate",
                 "url": "https://example.org/current"},
                {"title": "unsafe", "snippet": "unsafe",
                 "url": "http://unsafe.org/"},
            ]

        answer = lookup_live_evidence("Bitcoin kaç TL?", search=search, now=now)
        self.assertIn("2026-11-23T13:00", answer)
        self.assertIn("2026 güncel", queries[0][0])
        self.assertEqual(queries[0][1], 7)
        self.assertIn("https://example.org/current", answer)
        self.assertIn("Published: 2026-11-23", answer)
        self.assertIn("A page retrieved today may contain outdated", answer)
        self.assertNotIn("http://unsafe", answer)
        self.assertNotIn("duplicate", answer)

    def test_explicit_historical_year_is_not_replaced(self):
        queries = []

        def search(query, max_results):
            queries.append(query)
            return [{"title": "Historic rate", "snippet": "Historical example",
                     "url": "https://example.org/archive"}]

        lookup_live_evidence(
            "2020'de dolar kuru ne kadardı?", search=search,
            now=datetime(2026, 11, 23, tzinfo=timezone.utc))
        self.assertIn("2020", queries[0])
        self.assertNotIn("2026 güncel", queries[0])

    def test_search_failure_must_not_generate_model_fact(self):
        self.assertEqual(lookup_live_evidence("Dolar kuru ne kadar?",
                         search=lambda q, max_results: []), "")
        def fail(q, max_results):
            raise RuntimeError("network down")
        self.assertEqual(lookup_live_evidence("Güncel haberler neler?",
                         search=fail), "")

    @patch.object(web, "_gemini_search")
    @patch.object(web, "_ddg_search")
    def test_all_search_modes_use_live_source_before_model(self, ddg, gemini):
        ddg.return_value = [{
            "title": "Current listing",
            "snippet": "A dated listing from the site",
            "url": "https://example.org/info",
            "date": "2026-11-23",
        }]
        calls = (
            lambda: web._search("test"),
            lambda: web._research("test"),
            lambda: web._price("test"),
            lambda: web._compare(["test-a", "test-b"], "features"),
        )
        for fn in calls:
            with self.subTest(fn=fn):
                text = fn()
                self.assertIn("https://example.org/info", text)
                self.assertIn("2026-11-23", text)
        gemini.assert_not_called()
        self.assertGreaterEqual(ddg.call_count, 5)

    @patch.object(web, "_gemini_search", side_effect=RuntimeError("offline"))
    @patch.object(web, "_ddg_search", return_value=[])
    def test_no_cached_answer_when_all_searches_fail(self, ddg, gemini):
        self.assertIn("No verified current", web._search("breaking news"))
        self.assertIn("No verified current", web._research("breaking news"))
        self.assertIn("No verified current", web._price("phone"))
        self.assertIn("No verified current", web._compare(["a", "b"], "price"))


if __name__ == "__main__":
    unittest.main()
