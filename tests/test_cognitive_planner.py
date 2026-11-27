from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from actions import background_tasks
from core.tasks.agents import AgentProfile
from core.tasks.cognitive_planner import create_workflow
from core.tasks.engine import TaskEngine


class CognitivePlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.engine = TaskEngine(root / "tasks", root / "reports", [], autostart=False, log=lambda *_: None)
        self.engine._agents = {"general": AgentProfile("general", tools=["notes", "write_file"], minutes=1),
                               "web": AgentProfile("web", tools=["search_web"], minutes=1)}

    def test_model_plan_becomes_real_dependency_graph(self):
        plan = {"nodes": [
            {"id": "a", "task": "Investigate", "agent": "web", "minutes": 1, "max_calls": 2},
            {"id": "b", "task": "Draft", "agent": "general", "minutes": 1, "max_calls": 2},
            {"id": "c", "task": "Combine", "agent": "general", "depends_on": ["a", "b"],
             "minutes": 1, "max_calls": 2, "alternatives": ["Rework the report"]}]}
        prompts = []
        def ask(prompt):
            prompts.append(prompt)
            return plan
        doc = create_workflow(self.engine, "Bir rapor hazırla", "silent",
                              {"max_nodes": 3, "max_minutes": 4, "max_calls": 8}, ask)
        self.assertIn("Bir rapor hazırla", prompts[0])
        self.assertIn("web", prompts[0])
        self.assertEqual(doc["limits"]["max_nodes"], 3)
        self.engine.cognitive.advance()
        self.assertIsNotNone(self.engine.get(doc["nodes"][0]["task_id"]))
        self.assertIsNotNone(self.engine.get(doc["nodes"][1]["task_id"]))
        self.assertIsNone(self.engine.get(doc["nodes"][2]["task_id"]))

    def test_invalid_unavailable_or_over_budget_plan_never_starts(self):
        responses = [None, {"nodes": [{"id": "a", "task": "x", "agent": "admin"}]},
                     {"nodes": [{"id": "a", "task": "x", "depends_on": ["a"]}]},
                     {"nodes": [{"id": "a", "task": "x", "max_calls": 2,
                                  "minutes": 1, "alternatives": ["again"]}]}]
        for response in responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                create_workflow(self.engine, "x", limits={"max_calls": 3}, ask=lambda _: response)
        self.assertEqual(self.engine.cognitive.all(), [])
        self.assertEqual(self.engine.store.all(), [])

    def test_more_than_six_nodes_with_explicit_limits_and_hard_ceiling(self):
        nodes = [{"id": f"n{i}", "task": "read", "minutes": 1, "max_calls": 1} for i in range(7)]
        doc = create_workflow(self.engine, "goal", limits={"max_nodes": 7, "max_minutes": 7, "max_calls": 7},
                              ask=lambda _: {"nodes": nodes})
        self.assertEqual(len(doc["nodes"]), 7)
        with self.assertRaises(ValueError):
            create_workflow(self.engine, "goal", limits={"max_nodes": 13}, ask=lambda _: {"nodes": nodes})
        with self.assertRaises(ValueError):
            create_workflow(self.engine, "goal", limits={"max_nodes": 6}, ask=lambda _: {"nodes": nodes})

    def test_model_cannot_grant_a_tool_to_an_agent(self):
        node = {"id": "a", "task": "work", "agent": "general", "tools": ["run_shell"]}
        doc = create_workflow(self.engine, "goal", ask=lambda _: {"nodes": [node]})
        self.assertNotIn("run_shell", doc["nodes"][0]["tools"])

    def test_conversation_action_calls_planner_and_starts_workflow(self):
        plan = {"nodes": [{"id": "a", "task": "draft", "minutes": 1, "max_calls": 1}]}
        with patch("core.tasks.desktop.ensure", return_value=self.engine), \
             patch("core.gemini.as_json", return_value=plan) as ask:
            answer = background_tasks.background_tasks({"action": "cognitive_auto", "task": "Yaz",
                     "limits": {"max_nodes": 2, "max_minutes": 2, "max_calls": 2}, "deliver": "silent"})
        self.assertIn("status=started", answer)
        self.assertTrue(ask.called)
        self.engine.cognitive.advance()
        self.assertEqual(len(self.engine.store.all()), 1)

    def test_provider_failure_does_not_fabricate_success(self):
        with patch("core.tasks.desktop.ensure", return_value=self.engine), \
             patch("core.gemini.as_json", return_value=None):
            answer = background_tasks.background_tasks({"action": "cognitive_auto", "task": "Yaz"})
        self.assertIn("status=failed", answer)
        self.assertEqual(self.engine.cognitive.all(), [])
