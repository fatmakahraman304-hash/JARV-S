from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from core.tasks.agents import AgentProfile
from core.tasks.cognitive_planner import suggest_alternative
from core.tasks.engine import TaskEngine


class AdaptiveCognitiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = self.new_engine()

    def new_engine(self):
        engine = TaskEngine(self.root / "tasks", self.root / "reports", [], autostart=False, log=lambda *_: None)
        engine._agents = {"general": AgentProfile("general", tools=["notes", "write_file"], minutes=1)}
        return engine

    def workflow(self, nodes=None, **kwargs):
        return self.engine.cognitive.create("Goal", nodes or [
            {"id": "a", "task": "First approach", "minutes": 1, "max_calls": 2}],
            "silent", limits=kwargs.get("limits", {"max_minutes": 10, "max_calls": 10}),
            max_replans=kwargs.get("max_replans", 1))

    def wait_workers(self, engine=None):
        engine = engine or self.engine
        deadline = time.monotonic() + 5
        while engine.cognitive._replanning and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(engine.cognitive._replanning)

    def test_new_alternative_runs_without_repeating_completed_node(self):
        doc = self.workflow([{"id": "a", "task": "Completed", "minutes": 1, "max_calls": 2},
                             {"id": "b", "task": "Failing", "minutes": 1, "max_calls": 2,
                              "depends_on": ["a"]}])
        self.engine.cognitive.advance()
        first = doc["nodes"][0]["task_id"]
        self.engine._finish(first, "done", result="completed result")
        self.engine.cognitive.advance()
        second = doc["nodes"][1]["task_id"]
        self.engine._finish(second, "failed", error="timeout secret-token")
        with patch("core.tasks.cognitive_planner.suggest_alternative", return_value="Use a different approach") as ask:
            self.engine.cognitive.advance()
            self.wait_workers()
        self.assertNotIn("secret-token", ask.call_args.args[2])
        saved = self.engine.cognitive.get(doc["id"])
        self.assertEqual(saved["nodes"][0]["status"], "done")
        self.assertEqual(saved["nodes"][0]["task_id"], first)
        self.assertEqual(saved["nodes"][1]["attempt"], 1)
        self.engine.cognitive.advance()
        new_id = saved["nodes"][1]["task_id"]
        self.assertIn("different approach", self.engine.get(new_id)["task"])
        self.engine._finish(new_id, "done", result="Finished")
        self.engine.cognitive.advance()
        self.assertEqual(self.engine.cognitive.get(doc["id"])["status"], "finished_unverified")
        self.assertEqual(len(self.engine.store.all()), 3)

    def test_prior_completed_write_blocks_even_predefined_alternative(self):
        doc = self.workflow([{"id": "a", "task": "Write", "minutes": 1, "max_calls": 2,
                              "alternatives": ["Again"]}])
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        self.engine.store.update(tid, cognitive_ledger={"x": {"status": "completed", "tool": "write_file"}})
        self.engine._finish(tid, "failed", error="after writing")
        with patch("core.tasks.cognitive_planner.suggest_alternative") as ask:
            self.engine.cognitive.advance()
        ask.assert_not_called()
        self.assertEqual(self.engine.cognitive.get(doc["id"])["status"], "needs_review")
        self.assertEqual(len(self.engine.store.all()), 1)

    def test_no_replan_without_remaining_budget(self):
        doc = self.workflow(limits={"max_minutes": 1, "max_calls": 2})
        self.engine.cognitive.advance()
        self.engine._finish(doc["nodes"][0]["task_id"], "failed", error="failed")
        with patch("core.tasks.cognitive_planner.suggest_alternative") as ask:
            self.engine.cognitive.advance()
        ask.assert_not_called()
        self.assertEqual(self.engine.cognitive.get(doc["id"])["status"], "failed")

    def test_replan_interrupted_by_restart_needs_review(self):
        from core.tasks.store import write_json
        doc = self.workflow()
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        self.engine._finish(tid, "failed", error="failed")
        doc = self.engine.cognitive.get(doc["id"])
        doc["nodes"][0]["replan"] = {"status": "started", "token": "unresolved"}
        doc["replans_used"] = 1
        write_json(self.engine.cognitive._path(doc["id"]), doc)
        recovered = self.new_engine()
        with patch("core.tasks.cognitive_planner.suggest_alternative") as ask:
            recovered.cognitive.advance()
        ask.assert_not_called()
        self.assertEqual(recovered.cognitive.get(doc["id"])["status"], "needs_review")
        self.assertEqual(len(recovered.store.all()), 1)

    def test_cancel_during_model_call_cannot_launch_alternative(self):
        doc = self.workflow()
        self.engine.cognitive.advance()
        self.engine._finish(doc["nodes"][0]["task_id"], "failed", error="failed")
        started, release = threading.Event(), threading.Event()
        def suggest(*_):
            started.set()
            self.assertTrue(release.wait(5))
            return "New strategy"
        with patch("core.tasks.cognitive_planner.suggest_alternative", side_effect=suggest):
            self.engine.cognitive.advance()
            self.assertTrue(started.wait(5))
            self.assertTrue(self.engine.cognitive.cancel(doc["id"]))
            release.set()
            self.wait_workers()
        self.assertEqual(self.engine.cognitive.get(doc["id"])["status"], "cancelled")
        self.assertEqual(len(self.engine.store.all()), 1)

    def test_parallel_replans_cannot_overcommit_remaining_budget(self):
        doc = self.workflow([{"id": "a", "task": "A", "minutes": 1, "max_calls": 2},
                             {"id": "b", "task": "B", "minutes": 1, "max_calls": 2}],
                            limits={"max_minutes": 3, "max_calls": 6}, max_replans=2)
        self.engine.cognitive.advance()
        for node in doc["nodes"]:
            self.engine._finish(node["task_id"], "failed", error="failed")
        started, release = threading.Event(), threading.Event()
        def suggest(*_):
            started.set()
            self.assertTrue(release.wait(5))
            return "Different"
        with patch("core.tasks.cognitive_planner.suggest_alternative", side_effect=suggest) as ask:
            self.engine.cognitive.advance()
            self.assertTrue(started.wait(5))
            self.engine.cognitive.advance()
            release.set()
            self.wait_workers()
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(self.engine.cognitive.get(doc["id"])["status"], "failed")
        self.assertEqual(len(self.engine.store.all()), 2)

    def test_real_scheduler_executes_one_model_generated_replan(self):
        finished = threading.Event()
        def ask(_system, turns, _decls):
            if "First approach" in turns[0]["text"]:
                from core.tasks.brain import NoModel
                raise NoModel("failed", transient=False)
            return {"text": "completed", "calls": []}
        def notify(event, _doc, _text):
            if event == "plan_finished_unverified":
                finished.set()
        engine = TaskEngine(self.root / "live", self.root / "reports", [], autostart=False,
                            notify=notify, tick=0.01, log=lambda *_: None, ask_fn=ask,
                            context_fn=lambda: {"assistant_name": "FRIDAY", "user_name": "", "language": "tr"})
        engine._agents = self.engine._agents
        doc = engine.cognitive.create("Goal", [{"id": "a", "task": "First approach", "minutes": 1,
                                                  "max_calls": 2}], "silent", max_replans=1)
        with patch("core.tasks.cognitive_planner.suggest_alternative", return_value="Different approach"):
            engine.start_scheduler()
            try:
                self.assertTrue(finished.wait(10))
                self.assertEqual(engine.cognitive.get(doc["id"])["nodes"][0]["attempt"], 1)
            finally:
                engine.shutdown(wait=2)

    def test_model_cannot_change_permissions_or_return_empty_task(self):
        for data in ({"task": "x", "agent": "admin"}, {"task": ""}, None):
            self.assertIsNone(suggest_alternative("g", "t", "failed", ask=lambda _: data))
        self.assertEqual(suggest_alternative("g", "t", "failed", ask=lambda _: {"task": "  new  "}), "new")
