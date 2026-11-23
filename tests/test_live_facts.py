"""No-network regression checks for live fixture freshness guard."""
from datetime import datetime, timezone
import unittest

from core.live_facts import needs_fixture_lookup, lookup_fixture_evidence


class FixtureFreshnessTests(unittest.TestCase):
    def test_fixture_question_triggers_lookup(self):
        for q in (
            "Fenerin maçı ne zaman?",
            "Fenerbahçe'nin sıradaki maçı ne zaman",
            "Galatasaray maçı saat kaçta",
            "When is the next match for Fenerbahce?",
            "Next game for Arsenal?",
        ):
            with self.subTest(question=q):
                self.assertTrue(needs_fixture_lookup(q))

    def test_non_fixture_questions_do_not_search(self):
        for q in (
            "Merhaba",
            "Fenerbahçe nasıl kuruldu?",
            "Bana maç atmosferini anlat",
            "Dün maçları izledim",
            "2023'te hangi takım şampiyondu?",
        ):
            with self.subTest(question=q):
                self.assertFalse(needs_fixture_lookup(q))

    def test_official_sources_first_and_current_date(self):
        queries = []

        def search(query, max_results):
            queries.append((query, max_results))
            return [
                {"title": "Blog fixture", "snippet": "Unverified date",
                 "url": "https://sports.example/match"},
                {"title": "UEFA scheduled fixture",
                 "snippet": "25 November 2026; Shakhtar vs Fenerbahce",
                 "url": "https://www.uefa.com/uefachampionsleague/match/123"},
            ]

        answer = lookup_fixture_evidence(
            "Fenerin maçı ne zaman?", search=search,
            now=datetime(2026, 11, 23, tzinfo=timezone.utc))
        self.assertEqual(queries[0][1], 7)
        self.assertIn("23 November 2026", queries[0][0])
        self.assertIn("2026-11-23", answer)
        self.assertLess(answer.index("UEFA scheduled fixture"),
                        answer.index("Blog fixture"))
        self.assertIn("Source: https://www.uefa.com/", answer)

    def test_no_evidence_when_search_fails(self):
        self.assertEqual(
            lookup_fixture_evidence("Fenerin maçı ne zaman?",
                                    search=lambda query, max_results: []), "")
        def fail(query, max_results):
            raise RuntimeError("offline")
        self.assertEqual(
            lookup_fixture_evidence("Fenerin maçı ne zaman?", search=fail), "")

    def test_rejects_non_https_and_unusable_pages(self):
        items = [
            {"title": "Bad", "snippet": "January 9", "url": "http://bad.example"},
            {"title": "Missing snippet", "url": "https://real.example"},
            {"title": "No URL", "snippet": "No reliable source"},
        ]
        self.assertEqual(
            lookup_fixture_evidence("Fenerin maçı ne zaman?",
                                    search=lambda query, max_results: items),
            "")


if __name__ == "__main__":
    unittest.main()
