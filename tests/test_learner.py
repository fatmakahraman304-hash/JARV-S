import unittest
from unittest import mock


class LearnerTest(unittest.TestCase):
    def test_apply_skips_known_and_empty(self):
        from memory import learner
        mem = {"relationships": {"anne": {"value": "Ayşe"}}}
        facts = [{"category": "relationships", "key": "anne", "value": "Ayşe"},
                 {"category": "preferences", "key": "kahve", "value": "şekersiz"},
                 {"category": "uydurma", "key": "x", "value": "y"},
                 {"category": "notes", "key": "", "value": "boş"}]
        self.assertEqual(learner.apply(facts, mem), {"preferences": {"kahve": {"value": "şekersiz"}},
                                                     "notes": {"x": {"value": "y"}}})
        self.assertEqual(learner.apply("bozuk", mem), {})

    def test_run_files_what_the_model_found(self):
        from memory import learner
        learner._buf[:] = [("user", "annemin adı Ayşe"), ("jarvis", "Not ettim"), ("user", "kahveyi şekersiz içerim")]
        saved = []
        with mock.patch("memory.memory_manager.load_memory", return_value={}), \
             mock.patch("memory.memory_manager.update_memory", side_effect=saved.append), \
             mock.patch("core.gemini.as_json", return_value=[{"category": "relationships", "key": "anne", "value": "Ayşe"}]) as aj:
            self.assertEqual(learner.run(), 1)
        self.assertIn("annemin adı Ayşe", aj.call_args[0][0])
        self.assertEqual(saved, [{"relationships": {"anne": {"value": "Ayşe"}}}])
        self.assertEqual(learner._buf, [])

    def test_too_little_to_learn(self):
        from memory import learner
        learner._buf[:] = [("user", "merhaba")]
        with mock.patch("core.gemini.as_json") as aj:
            self.assertEqual(learner.run(), 0)
        aj.assert_not_called()


if __name__ == "__main__":
    unittest.main()
