import unittest
from unittest import mock


class TodoListTest(unittest.TestCase):
    def setUp(self):
        self.mem = {"notes": {"başka not": {"value": "x"}}}

        def remember(key, value, category="notes"):
            self.mem.setdefault(category, {})[key] = {"value": value}

        def forget(key, category="notes"):
            self.mem.get(category, {}).pop(key, None)
        self.patches = [mock.patch("memory.memory_manager.load_memory", side_effect=lambda: self.mem),
                        mock.patch("memory.memory_manager.remember", side_effect=remember),
                        mock.patch("memory.memory_manager.forget", side_effect=forget)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_add_list_done_use_the_shared_key_format(self):
        from plugins import todo_list
        self.assertIn("boş", todo_list.run({"action": "list"}))
        todo_list.run({"action": "add", "item": "Süt al"})
        todo_list.run({"action": "add", "item": "Faturayı öde"})
        self.assertIn("yapılacak: Süt al", self.mem["notes"])           # same key as web/app.js todoTool
        self.assertEqual(todo_list.run({"action": "list"}), "1. Süt al\n2. Faturayı öde")
        self.assertIn("Faturayı öde", todo_list.run({"action": "done", "item": "fatura"}))
        self.assertNotIn("yapılacak: Faturayı öde", self.mem["notes"])
        self.assertIn("bulamadım", todo_list.run({"action": "done", "item": "yok"}))
        todo_list.run({"action": "clear_done"})
        self.assertIn("yapılacak: Süt al", self.mem["notes"])
        self.assertIn("1 madde", todo_list.run({"action": "clear"}))
        self.assertIn("başka not", self.mem["notes"])                     # other notes untouched

    def test_ambiguous_completion_preserves_tasks_and_exact_match_wins(self):
        from plugins import todo_list
        for item in ("İlaç al", "İlaç al ve ara"):
            todo_list.run({"action": "add", "item": item})
        self.assertIn("Hangi madde", todo_list.run({"action": "done", "item": "ilaç"}))
        self.assertIn("Tamamlandı", todo_list.run({"action": "done", "item": "ilaç al"}))
        self.assertEqual(todo_list.run({"action": "list"}), "1. İlaç al ve ara")


if __name__ == "__main__":
    unittest.main()
