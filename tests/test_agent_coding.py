"""Stronger coding: agent mode (Claude Code / Codex working in the folder) and
exact edit blocks for big files."""
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import agent_coding


class SnapshotTest(unittest.TestCase):
    def test_diff_and_restore(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.py").write_text("x = 1\n")
            (root / "b.py").write_text("y = 2\n")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "big.js").write_text("skip")
            before = agent_coding.snapshot(root)
            self.assertNotIn("node_modules/big.js", before)
            (root / "a.py").write_text("x = 10\n")
            (root / "c.py").write_text("new\n")
            (root / "b.py").unlink()
            after = agent_coding.snapshot(root)
            self.assertEqual(agent_coding.diff(before, after), (["a.py"], ["c.py"], ["b.py"]))
            agent_coding.restore(root, before, list(after))
            self.assertEqual((root / "a.py").read_text(), "x = 1\n")
            self.assertEqual((root / "b.py").read_text(), "y = 2\n")
            self.assertFalse((root / "c.py").exists())


class ClaudeStreamTest(unittest.TestCase):
    def test_events(self):
        logged = []
        tool = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "app.py"}}]}}
        self.assertEqual(agent_coding._claude_event(json.dumps(tool), logged.append), "")
        self.assertIn("Düzenliyor: app.py", logged[0])
        done = {"type": "result", "is_error": False, "result": "Testler geçti."}
        self.assertEqual(agent_coding._claude_event(json.dumps(done), logged.append), "Testler geçti.")
        with self.assertRaises(RuntimeError):
            agent_coding._claude_event(json.dumps({"type": "result", "is_error": True, "result": "x"}), logged.append)
        self.assertEqual(agent_coding._claude_event("not json", logged.append), "")

    def test_brief_keeps_rules_and_task(self):
        b = agent_coding._brief("sepete indirim ekle", "Qt only on main thread", "fix: tests fail")
        self.assertIn("sepete indirim ekle", b)
        self.assertIn("Qt only on main thread", b)
        self.assertIn("fix: tests fail", b)


class EditBlocksTest(unittest.TestCase):
    def setUp(self):
        from actions import dev_agent
        self.da = dev_agent

    def test_applies_exact_and_refuses_ambiguous(self):
        cur = "def f():\n    return 1\n\ndef g():\n    return 1\n"
        ok = "<<<<<<< SEARCH\ndef f():\n    return 1\n=======\ndef f():\n    return 2\n>>>>>>> REPLACE"
        self.assertEqual(self.da._apply_edit_blocks(cur, ok), "def f():\n    return 2\n\ndef g():\n    return 1\n")
        amb = "<<<<<<< SEARCH\n    return 1\n=======\n    return 3\n>>>>>>> REPLACE"
        self.assertIsNone(self.da._apply_edit_blocks(cur, amb))
        self.assertIsNone(self.da._apply_edit_blocks(cur, "here is the whole file instead"))

    def test_all_or_nothing(self):
        cur = "a\nb\nc\n"
        two = ("<<<<<<< SEARCH\na\n=======\nA\n>>>>>>> REPLACE\n"
               "<<<<<<< SEARCH\nzzz\n=======\nZ\n>>>>>>> REPLACE")
        self.assertIsNone(self.da._apply_edit_blocks(cur, two))

    def test_big_file_uses_blocks(self):
        cur = "\n".join(f"line_{i} = {i}" for i in range(2000)) + "\n"
        reply = "<<<<<<< SEARCH\nline_5 = 5\n=======\nline_5 = 55\n>>>>>>> REPLACE"
        model = mock.Mock()
        model.generate_content.return_value = mock.Mock(text=reply)
        with mock.patch.object(self.da, "_get_model", return_value=model):
            out = self.da._write_change({"path": "big.py", "action": "edit", "what": "x"},
                                        {"changes": []}, "change line 5", "", cur)
        self.assertIn("line_5 = 55\n", out)
        self.assertIn("line_1999 = 1999", out)
        self.assertEqual(model.generate_content.call_count, 1)


class AgentModeTest(unittest.TestCase):
    def setUp(self):
        from actions import dev_agent
        self.da = dev_agent

    def test_only_agent_providers(self):
        self.assertFalse(self.da._use_agent(""))
        self.assertFalse(self.da._use_agent("openai_compat@openai"))
        with mock.patch.object(agent_coding, "available", return_value=True):
            self.assertTrue(self.da._use_agent("claude_code"))
            with mock.patch("memory.config_manager.get_plugin_setting", return_value=False):
                self.assertFalse(self.da._use_agent("codex_cli"))

    def test_improve_with_agent_restores_secrets_and_registers_undo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.py").write_text("def total(x):\n    return x\n")
            (root / ".env").write_text("KEY=secret\n")

            def fake_run(provider, folder, instruction, guide, extra, log):
                (folder / "app.py").write_text("def total(x):\n    return x * 2\n")
                (folder / "test_app.py").write_text("from app import total\n")
                (folder / ".env").write_text("KEY=leaked\n")
                return "İndirim eklendi, testler geçti."
            undo = {}
            with mock.patch.object(agent_coding, "run", side_effect=fake_run), \
                 mock.patch.object(self.da, "_agent_checks", return_value={}), \
                 mock.patch.object(self.da, "_open_vscode"), \
                 mock.patch.object(self.da, "_refresh_brief"), \
                 mock.patch("core.undo.push_undo", side_effect=lambda label, fn: undo.setdefault("fn", fn)):
                msg = self.da._improve_with_agent(root, "indirim", "", None, None,
                                                  {"app.py": "def total(x):\n    return x\n"},
                                                  "claude_code", None, 0.0, False)
            self.assertIn("app.py", msg)
            self.assertIn("test_app.py", msg)
            self.assertEqual((root / ".env").read_text(), "KEY=secret\n")   # secrets put back
            undo["fn"]()
            self.assertEqual((root / "app.py").read_text(), "def total(x):\n    return x\n")
            self.assertFalse((root / "test_app.py").exists())

    def test_agent_failure_leaves_folder_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.py").write_text("a = 1\n")

            def boom(provider, folder, *a, **k):
                (folder / "app.py").write_text("half written")
                raise RuntimeError("Claude Code oturumu kapalı.")
            with mock.patch.object(agent_coding, "run", side_effect=boom):
                with self.assertRaises(RuntimeError):
                    self.da._improve_with_agent(root, "x", "", None, None, {}, "claude_code",
                                                None, 0.0, False)
            self.assertEqual((root / "app.py").read_text(), "a = 1\n")


if __name__ == "__main__":
    unittest.main()


class RouterTest(unittest.TestCase):
    """The best model first; the next one when it hits its limit; back to the
    best once its rest is over."""

    def setUp(self):
        from core import coding_router
        self.r = coding_router
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(coding_router, "_COOL_FILE", Path(self.tmp.name) / "cool.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_order_and_rest(self):
        both = lambda p: True
        self.assertEqual(self.r.ladder("openai_compat@openai", both),
                         ["claude_code", "codex_cli", "openai_compat@openai", ""])
        self.assertEqual(self.r.ladder("", lambda p: p == "codex_cli"), ["codex_cli", ""])
        secs = self.r.rest("claude_code", RuntimeError("Claude Code kullanım sınırına ulaşıldı."))
        self.assertEqual(secs, self.r.LIMIT_REST)
        self.assertEqual(self.r.ladder("", both), ["codex_cli", ""])
        with mock.patch.object(self.r.time, "time", return_value=time.time() + self.r.LIMIT_REST + 5):
            self.assertEqual(self.r.ladder("", both), ["claude_code", "codex_cli", ""])
        self.assertEqual(self.r.rest("codex_cli", RuntimeError("Codex oturumu doğrulanamadı")), self.r.DOWN_REST)

    def test_what_counts_as_switchable(self):
        self.assertTrue(self.r.should_switch(RuntimeError("429 Too Many Requests")))
        self.assertTrue(self.r.should_switch(RuntimeError("Claude Code oturumu kapalı.")))
        self.assertFalse(self.r.should_switch(RuntimeError("SyntaxError in your request")))

    def test_dev_agent_switches_text_model_on_limit(self):
        from actions import dev_agent
        calls = []

        def claude(prompt):
            calls.append("claude")
            raise RuntimeError("Claude Code kullanım sınırına ulaşıldı.")

        def codex(prompt):
            calls.append("codex")
            return mock.Mock(text="ok")
        with mock.patch.object(self.r, "ladder", side_effect=lambda chosen="": [
                p for p in ("claude_code", "codex_cli") if not self.r.resting(p)] + [""]), \
             mock.patch.object(dev_agent.claude_coding, "generate_content", side_effect=claude), \
             mock.patch.object(dev_agent.codex_coding, "generate_content", side_effect=codex):
            out = dev_agent._get_model().generate_content("yaz")
            self.assertEqual(out.text, "ok")
            self.assertEqual(calls, ["claude", "codex"])
            dev_agent._get_model().generate_content("yine")      # claude rests now: straight to codex
            self.assertEqual(calls, ["claude", "codex", "codex"])

    def test_agents_switch_on_limit(self):
        from actions import dev_agent
        tried = []

        def job(ag):
            tried.append(ag)
            if ag == "claude_code":
                raise RuntimeError("Claude Code çalışamadı: Claude Code kullanım sınırına ulaşıldı.")
            return f"done by {ag}"
        self.assertEqual(dev_agent._with_agents(["claude_code", "codex_cli"], job, None), "done by codex_cli")
        self.assertEqual(tried, ["claude_code", "codex_cli"])
        self.assertTrue(self.r.resting("claude_code") > 0)
        with self.assertRaises(RuntimeError):      # a real error is not hidden by switching
            dev_agent._with_agents(["codex_cli"], lambda ag: (_ for _ in ()).throw(RuntimeError("bad diff")), None)
