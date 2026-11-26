import unittest

from plugins import assistant_help


class AssistantHelpTests(unittest.TestCase):
    def test_declared_topics_have_guidance(self):
        topics = assistant_help.PLUGIN["parameters"]["properties"]["topic"]["enum"]
        self.assertEqual(set(topics), set(assistant_help._GUIDE) | {"index"})
        for topic in assistant_help._GUIDE:
            with self.subTest(topic=topic):
                result = assistant_help.run({"topic": topic})
                self.assertIn("Proje içi başvuru:", result)
                self.assertGreater(len(result), 60)

    def test_index_lists_all_topics(self):
        result = assistant_help.run({"topic": "index"})
        for key in assistant_help._GUIDE:
            self.assertIn(key + ":", result)

    def test_unknown_or_malformed_inputs_do_not_invent_guidance(self):
        for payload in ({"topic": "unknown"}, {"topic": ["audio"]}, {"topic": 10}):
            self.assertIn("doğrulanmış kılavuz bölümü yok", assistant_help.run(payload))
        self.assertIn("Bölümler:", assistant_help.run(None))

    def test_normalizes_topic(self):
        self.assertEqual(assistant_help.run({"topic": " AUDIO "}),
                         assistant_help.run({"topic": "audio"}))

    def test_no_live_status_claim(self):
        self.assertIn("canlı bir teşhis sonucu değildir", assistant_help.run({"topic": "diagnostics"}))
        self.assertIn("bağlantıyı test etmez", assistant_help.run({"topic": "providers"}))


if __name__ == "__main__":
    unittest.main()
