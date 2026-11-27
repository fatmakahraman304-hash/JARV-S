from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from actions import background_tasks
from core import outcome
from core.tasks.agents import AgentProfile
from core.tasks.cognitive_tools import CognitiveTools
from core.tasks.engine import TaskEngine


class CognitiveEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.events = []
        self.engine = self.new_engine()

    def new_engine(self):
        eng = TaskEngine(self.base / "tasks", self.base / "reports", [], autostart=False,
                         notify=lambda *args: self.events.append(args), log=lambda *_: None)
        eng._agents = {"general": AgentProfile("general", title="General", tools=["write_file", "notes"], minutes=1),
                       "private": AgentProfile("private", title="Private", tools=["recall_memory"], minutes=1),
                       "web": AgentProfile("web", title="Web", tools=["search_web"], minutes=1)}
        return eng

    def graph(self):
        return self.engine.cognitive.create("Birleşik çalışma", [
            {"id": "a", "task": "First", "agent": "general"},
            {"id": "b", "task": "Second", "agent": "general"},
            {"id": "c", "task": "Combine", "agent": "general", "depends_on": ["a", "b"]}], "silent")

    def test_dependencies_schedule_independent_nodes_and_wait_for_both(self):
        doc = self.graph()
        a, b, c = [n["task_id"] for n in doc["nodes"]]
        self.engine.cognitive.advance()
        self.assertIsNotNone(self.engine.get(a))
        self.assertIsNotNone(self.engine.get(b))
        self.assertIsNone(self.engine.get(c))
        self.engine._finish(a, "done", result="source A")
        self.engine.cognitive.advance()
        self.assertIsNone(self.engine.get(c))
        self.engine._finish(b, "done", result="source B")
        self.engine.cognitive.advance()
        combined = self.engine.get(c)["task"]
        self.assertIn("source A", combined)
        self.assertIn("source B", combined)
        self.assertIn("<<<UNTRUSTED source=dependency-result>>>", combined)
        self.engine._finish(c, "done", result="Combined")
        self.engine.cognitive.advance()
        self.assertEqual(self.engine.cognitive.get(doc["id"])["status"], "finished_unverified")

    def test_explicit_alternative_runs_after_a_failed_attempt(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Primary",
              "alternatives": ["Alternative"], "agent": "general"}], "silent")
        self.engine.cognitive.advance()
        first = doc["nodes"][0]["task_id"]
        self.engine._finish(first, "failed", error="not available")
        self.engine.cognitive.advance()
        current = self.engine.cognitive.get(doc["id"])["nodes"][0]
        self.assertEqual(current["attempt"], 1)
        self.assertIsNone(self.engine.get(current["task_id"]))
        self.engine.cognitive.advance()
        self.assertIn("Alternative", self.engine.get(current["task_id"])["task"])
        self.assertIn("unavailable", self.engine.get(current["task_id"])["task"])
        self.assertIsNotNone(self.engine.get(first))

    def test_tool_budget_is_enforced_and_completed_write_is_not_replayed(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Task", "max_calls": 2}], "silent")
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        calls = []
        class Tool:
            names = ["write_file", "system_snapshot"]
            def execute(self, name, args):
                calls.append((name, args))
                return outcome.done(name, observed=True)
        tool = CognitiveTools(self.engine, tid, Tool())
        args = {"path": "x.txt", "content": "x"}
        self.assertIn("status=done", tool.execute("write_file", args))
        self.assertIn("status=done", tool.execute("write_file", args))
        self.assertEqual(len(calls), 1)
        tool.execute("system_snapshot", {})
        self.assertIn("status=failed", tool.execute("system_snapshot", {}))
        self.assertEqual(len(calls), 2)
        self.assertTrue(self.engine.get(tid)["cognitive_budget_exhausted"])

    def test_cognitive_workflow_does_not_offer_unjournaled_file_processor(self):
        from core.tasks.tools import TaskTools
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Inspect"}], "silent")
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        base = TaskTools(self.base / "sandbox", ["file_processor", "write_file"], log=lambda _: None)
        guarded = CognitiveTools(self.engine, tid, base)
        self.assertNotIn("file_processor", guarded.names)
        self.assertNotIn("file_processor", [d["name"] for d in guarded.declarations()])
        self.assertIn("status=failed", guarded.execute("file_processor", {"action": "extract"}))

    def test_unlisted_cloud_workspace_cannot_be_called_even_if_model_invents_it(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Inspect"}], "silent")
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        class CloudTools:
            names = ["write_file"]
            def declarations(self):
                return [{"name": "write_file"}, {"name": "workspace"}]
            def execute(self, name, args):
                raise AssertionError("unlisted workspace must not be called")
        guarded = CognitiveTools(self.engine, tid, CloudTools())
        self.assertEqual([d["name"] for d in guarded.declarations()], ["write_file"])
        self.assertIn("status=failed", guarded.execute("workspace", {"action": "write"}))

    def test_new_underlying_tools_are_not_automatically_authorized(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Inspect"}], "silent")
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        class FutureTools:
            names = ["write_file", "future_control"]
            def declarations(self):
                return [{"name": n} for n in self.names]
            def execute(self, name, args):
                raise AssertionError("future tool must not execute")
        guarded = CognitiveTools(self.engine, tid, FutureTools())
        self.assertEqual([d["name"] for d in guarded.declarations()], ["write_file"])
        self.assertIn("status=failed", guarded.execute("future_control", {}))

    def test_interrupted_write_requires_review_after_restart_without_alternative(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Write",
              "alternatives": ["Try something else"]}], "silent")
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        self.engine.store.update(tid, status="running", cognitive_ledger={"hash": {"status": "started", "tool": "write_file"}})
        resumed = self.new_engine()
        self.assertEqual(resumed.get(tid)["status"], "needs_review")
        resumed.cognitive.advance()
        saved = resumed.cognitive.get(doc["id"])
        self.assertEqual(saved["status"], "needs_review")
        self.assertEqual(saved["nodes"][0]["attempt"], 0)
        self.assertEqual(len(resumed.store.all()), 1)

    def test_restart_after_tasks_created_but_before_graph_checkpoint(self):
        doc = self.graph()
        with patch("core.tasks.cognitive.write_json", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                self.engine.cognitive.advance()
        self.assertEqual(len(self.engine.store.all()), 2)
        recovered = self.new_engine()
        recovered.cognitive.advance()
        self.assertEqual(len(recovered.store.all()), 2)
        saved = recovered.cognitive.get(doc["id"])
        self.assertEqual([n["status"] for n in saved["nodes"]], ["queued", "queued", "pending"])

    def test_cancel_is_resumed_and_future_nodes_stay_stopped(self):
        doc = self.graph()
        self.engine.cognitive.advance()
        a, b, c = [n["task_id"] for n in doc["nodes"]]
        self.engine.store.update(a, status="running")
        self.engine._flags[a] = {"cancel": False, "finish": False, "halt": False}
        self.assertTrue(self.engine.cognitive.cancel(doc["id"]))
        self.assertTrue(self.engine._flags[a]["cancel"])
        self.assertEqual(self.engine.get(b)["status"], "cancelled")
        self.assertEqual(self.engine.cognitive.get(doc["id"])["status"], "cancelling")
        recovered = self.new_engine()
        recovered.cognitive.advance()
        self.assertEqual(recovered.cognitive.get(doc["id"])["status"], "cancelled")
        self.assertIsNone(recovered.get(c))

    def test_exception_after_a_write_is_not_automatically_repeated(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Write",
              "alternatives": ["Alternative"]}], "silent")
        self.engine.cognitive.advance()
        tid = doc["nodes"][0]["task_id"]
        calls = []
        class InterruptedTool:
            names = ["write_file"]
            def execute(self, name, _args):
                calls.append(name)
                raise OSError("after partial write")
        guarded = CognitiveTools(self.engine, tid, InterruptedTool())
        answer = guarded.execute("write_file", {"path": "x", "content": "y"})
        self.assertIn("status=unverified", answer)
        self.assertIn("retry_automatically=false", answer)
        self.engine.store.update(tid, status="running")
        recovered = self.new_engine()
        recovered.cognitive.advance()
        self.assertEqual(recovered.cognitive.get(doc["id"])["status"], "needs_review")
        self.assertEqual(calls, ["write_file"])

    def test_private_result_is_withheld_from_web_node(self):
        doc = self.engine.cognitive.create("Hedef", [
            {"id": "a", "task": "private", "agent": "private"},
            {"id": "b", "task": "search", "agent": "web", "depends_on": ["a"]}], "silent")
        self.engine.cognitive.advance()
        self.engine._finish(doc["nodes"][0]["task_id"], "done", result="private secret")
        self.engine.cognitive.advance()
        text = self.engine.get(doc["nodes"][1]["task_id"])["task"]
        self.assertNotIn("private secret", text)
        self.assertIn("withheld", text)

    def test_file_verification_failure_uses_alternative_and_preserves_files(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Write", "verification": "file_written",
                                                       "alternatives": ["Produce a file"]}], "silent")
        self.engine.cognitive.advance()
        first = doc["nodes"][0]["task_id"]
        self.engine._finish(first, "done", result="I think I wrote it")
        self.engine.cognitive.advance()
        node = self.engine.cognitive.get(doc["id"])["nodes"][0]
        self.assertEqual(node["attempt"], 1)
        self.engine.cognitive.advance()
        second = node["task_id"]
        folder = self.engine.store.workdir(second) / "files"
        folder.mkdir(parents=True)
        (folder / "report.txt").write_text("actual", encoding="utf-8")
        self.engine.store.save_turns(second, [
            {"role": "model", "calls": [{"id": "c", "name": "write_file", "args": {"path": "report.txt", "content": "actual"}}]},
            {"role": "tool", "results": [{"id": "c", "name": "write_file", "result": "status=done action=write_file"}]}])
        self.engine._finish(second, "done", result="file is ready")
        self.engine.cognitive.advance()
        saved = self.engine.cognitive.get(doc["id"])
        self.assertEqual(saved["status"], "finished_unverified")
        self.assertEqual(saved["nodes"][0]["artifacts"][0]["status"], "verified")

    def test_invalid_cycle_and_unbounded_budgets_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.cognitive.create("x", [{"id": "a", "task": "a", "depends_on": ["b"]},
                                                {"id": "b", "task": "b", "depends_on": ["a"]}])
        with self.assertRaises(ValueError):
            self.engine.cognitive.create("x", [{"id": "a", "task": "a", "max_calls": 101}])

    def test_user_can_revise_only_unstarted_node(self):
        doc = self.graph()
        self.engine.cognitive.advance()
        self.assertFalse(self.engine.cognitive.revise(doc["id"], "a", "new"))
        self.assertTrue(self.engine.cognitive.revise(doc["id"], "c", "updated task"))
        self.assertEqual(self.engine.cognitive.get(doc["id"])["nodes"][2]["task"], "updated task")

    def test_revising_an_unstarted_alternative_changes_the_next_attempt(self):
        doc = self.engine.cognitive.create("Hedef", [{"id": "a", "task": "Primary",
              "alternatives": ["old alternative"]}], "silent")
        self.engine.cognitive.advance()
        self.engine._finish(doc["nodes"][0]["task_id"], "failed", error="failed")
        self.engine.cognitive.advance()
        self.assertTrue(self.engine.cognitive.revise(doc["id"], "a", "new alternative"))
        self.engine.cognitive.advance()
        node = self.engine.cognitive.get(doc["id"])["nodes"][0]
        self.assertIn("new alternative", self.engine.get(node["task_id"])["task"])

    def test_cognitive_actions_are_available_to_the_conversation(self):
        with patch("core.tasks.desktop.ensure", return_value=self.engine):
            result = background_tasks.background_tasks({"action": "cognitive_start", "task": "Hedef",
                     "nodes": [{"id": "a", "task": "Araştır"}, {"id": "b", "task": "Yaz", "depends_on": ["a"]}]})
            self.assertIn("status=started", result)
            doc = self.engine.cognitive.all()[0]
            self.assertIn(doc["id"], background_tasks.background_tasks({"action": "cognitive_list"}))
            self.assertIn("workflow_status=running", background_tasks.background_tasks(
                {"action": "cognitive_status", "workflow_id": doc["id"]}))

    def test_real_scheduler_runs_independent_nodes_in_parallel(self):
        barrier = threading.Barrier(2, timeout=10)
        done = threading.Event()
        def ask(_system, turns, _decls):
            text = turns[0]["text"]
            if "Root task" in text:
                barrier.wait()
            return {"text": "Produced report", "calls": []}
        def notify(event, _doc, _text):
            if event == "plan_finished_unverified":
                done.set()
        eng = TaskEngine(self.base / "live", self.base / "reports", [], autostart=False, max_parallel=2,
                         tick=0.01, ask_fn=ask, notify=notify,
                         context_fn=lambda: {"assistant_name": "FRIDAY", "user_name": "", "language": "tr"})
        eng._agents = {"general": AgentProfile("general", title="General", tools=["notes"], minutes=1)}
        doc = eng.cognitive.create("Hedef", [{"id": "a", "task": "Root task A"},
                    {"id": "b", "task": "Root task B"},
                    {"id": "c", "task": "Merge reports", "depends_on": ["a", "b"]}], "silent")
        eng.start_scheduler()
        try:
            self.assertTrue(done.wait(20))
            self.assertEqual(eng.cognitive.get(doc["id"])["status"], "finished_unverified")
        finally:
            eng.shutdown(wait=2)

    def test_real_scheduler_stops_when_tool_call_budget_is_exceeded(self):
        done = threading.Event()
        def ask(_system, _turns, _decls):
            return {"text": "", "calls": [
                {"id": "one", "name": "write_file", "args": {"path": "one.txt", "content": "one"}},
                {"id": "two", "name": "write_file", "args": {"path": "two.txt", "content": "two"}}]}
        def notify(event, _doc, _text):
            if event == "plan_failed":
                done.set()
        eng = TaskEngine(self.base / "live-budget", self.base / "reports", [], autostart=False,
                         tick=0.01, ask_fn=ask, notify=notify,
                         context_fn=lambda: {"assistant_name": "FRIDAY", "user_name": "", "language": "tr"})
        eng._agents = {"general": AgentProfile("general", title="General", tools=["write_file"], minutes=1)}
        doc = eng.cognitive.create("Hedef", [{"id": "a", "task": "Write two files", "max_calls": 1}], "silent")
        eng.start_scheduler()
        try:
            self.assertTrue(done.wait(20))
            self.assertEqual(eng.cognitive.get(doc["id"])["status"], "failed")
            folder = eng.store.workdir(doc["nodes"][0]["task_id"]) / "files"
            self.assertEqual((folder / "one.txt").read_text(encoding="utf-8"), "one")
            self.assertFalse((folder / "two.txt").exists())
        finally:
            eng.shutdown(wait=2)
