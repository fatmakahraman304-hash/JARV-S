import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from core.tasks import store


class TaskStoreAtomicTests(unittest.TestCase):
    def test_simultaneous_writes_have_independent_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "checkpoint.json"
            barrier = threading.Barrier(2, timeout=5)
            real_replace = store.os.replace
            errors = []

            def replace_after_both_are_ready(src, dst):
                barrier.wait()
                real_replace(src, dst)

            def writer(number):
                try:
                    store.write_json(target, {"writer": number, "data": str(number) * 2000})
                except Exception as exc:
                    errors.append(exc)

            with patch.object(store.os, "replace", side_effect=replace_after_both_are_ready):
                threads = [threading.Thread(target=writer, args=(n,)) for n in (1, 2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            result = json.loads(target.read_text(encoding="utf-8"))
            self.assertIn(result["writer"], (1, 2))
            self.assertEqual(result["data"], str(result["writer"]) * 2000)
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_failed_write_keeps_previous_file_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "checkpoint.json"
            target.write_text('{"old": true}', encoding="utf-8")
            with patch.object(store.os, "replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    store.write_json(target, {"new": True})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"old": True})
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_failed_create_and_mutation_do_not_change_visible_state(self):
        with tempfile.TemporaryDirectory() as directory:
            tasks = store.TaskStore(Path(directory))
            with patch.object(store, "write_json", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    tasks.create({"id": "new", "status": "queued"})
            self.assertIsNone(tasks.get("new"))

            original = {"id": "one", "status": "running", "events": ["started"]}
            tasks.create(original)
            original["events"].append("external mutation")
            with patch.object(store, "write_json", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    tasks.mutate("one", lambda task: (task.update(status="done"), task["events"].append("done")))
            expected = {"id": "one", "status": "running", "events": ["started"]}
            self.assertEqual(tasks.get("one"), expected)
            self.assertEqual(store.TaskStore(Path(directory)).get("one"), expected)
