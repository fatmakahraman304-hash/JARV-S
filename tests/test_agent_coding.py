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


class SafeRollbackTest(unittest.TestCase):
    def test_restores_only_changed_files_and_preserves_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("old")
            (root / "unchanged.py").write_text("original")
            before = agent_coding.snapshot(root)
            (root / "a.py").write_text("agent version")
            (root / "new.py").write_text("new")
            after = agent_coding.snapshot(root)
            # A user edits an unrelated file after the agent completed.
            (root / "unchanged.py").write_text("new user version")
            conflicts = agent_coding.restore_checked(root, before, after)
            self.assertFalse(conflicts)
            self.assertEqual((root / "a.py").read_text(), "old")
            self.assertEqual((root / "unchanged.py").read_text(), "new user version")
            self.assertFalse((root / "new.py").exists())

    def test_concurrent_edit_to_changed_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("old")
            before = agent_coding.snapshot(root)
            (root / "a.py").write_text("agent")
            after = agent_coding.snapshot(root)
            (root / "a.py").write_text("new user work")
            conflicts = agent_coding.restore_checked(root, before, after)
            self.assertTrue(any("edited after agent" in c for c in conflicts))
            self.assertEqual((root / "a.py").read_text(), "new user work")

    def test_missing_restore_bytes_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("old")
            before = agent_coding.snapshot(root)
            original = before["a.py"]
            before["a.py"] = (original[0], original[1], original[2], None)
            (root / "a.py").write_text("agent")
            after = agent_coding.snapshot(root)
            conflicts = agent_coding.restore_checked(root, before, after)
            self.assertTrue(any("no checkpoint bytes" in c for c in conflicts))
            self.assertEqual((root / "a.py").read_text(), "agent")


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
            self.assertTrue(self.da._use_agent("aether_agent"))
            self.assertFalse(self.da._use_agent("claude_code"))
            self.assertFalse(self.da._use_agent("codex_cli"))

    def test_improve_with_agent_restores_secrets_and_registers_undo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.py").write_text("def total(x):\n    return x\n")
            (root / ".env").write_text("KEY=secret\n")
            (root / ".env.local").write_text("private")

            def fake_run(provider, folder, instruction, guide, extra, log):
                (folder / "app.py").write_text("def total(x):\n    return x * 2\n")
                (folder / "test_app.py").write_text("from app import total\n")
                (folder / ".env").write_text("KEY=leaked\n")
                (folder / ".env.local").unlink()
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
            self.assertNotIn("testler geçti", msg)
            self.assertEqual((root / ".env.local").read_text(), "private")
            self.assertIn("app.py", msg)
            self.assertIn("test_app.py", msg)
            self.assertIn("otomatik test komutu algılanmadı", msg)
            self.assertNotIn("FRIDAY'ın kendi testleri başarılı", msg)
            self.assertEqual((root / ".env").read_text(), "KEY=secret\n")   # secrets put back
            undo["fn"]()
            self.assertEqual((root / "app.py").read_text(), "def total(x):\n    return x\n")
            self.assertFalse((root / "test_app.py").exists())

    def test_agent_verification_failure_rolls_back_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.py").write_text("original")

            def changes(provider, folder, instruction, guide, extra, log):
                (folder / "app.py").write_text("failing update")
                return "changed"

            with mock.patch.object(agent_coding, "run", side_effect=changes), \
                 mock.patch.object(self.da, "_agent_checks",
                                   return_value={"app.py": "regression"}), \
                 mock.patch.object(self.da, "_open_vscode"), \
                 mock.patch.object(self.da, "_refresh_brief"):
                with self.assertRaisesRegex(RuntimeError, "geri alındı"):
                    self.da._improve_with_agent(root, "fix", "", {}, None,
                                                {"app.py": "original"},
                                                "aether_agent", None, 0.0, False)
            self.assertEqual((root / "app.py").read_text(), "original")

    def test_cancel_during_second_fix_round_reverts_all_changes(self):
        from core.aether_agent import AgentCancelled
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "app.py").write_text("original")
            rounds = []

            def run(provider, folder, *args, **kwargs):
                rounds.append(True)
                (folder / "app.py").write_text("partial code")
                if len(rounds) == 2:
                    raise AgentCancelled("user cancelled")
                return "first round"

            with mock.patch.object(agent_coding, "run", side_effect=run), \
                 mock.patch.object(self.da, "_agent_checks",
                                   return_value={"app.py": "broken"}), \
                 mock.patch.object(self.da, "_open_vscode"):
                with self.assertRaises(AgentCancelled):
                    self.da._improve_with_agent(root, "fix", "", {}, None,
                                                {"app.py": "original"},
                                                "aether_agent", None, 0.0, False)
            self.assertEqual((root / "app.py").read_text(), "original")


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
        self.assertEqual(self.r.ladder("openai_compat@deepseek", both),
                         ["aether_agent", ""])  # Eski kayıt yeniden etkinleşmez
        self.assertEqual(self.r.ladder("claude_code", both), ["aether_agent", ""])
        self.assertEqual(self.r.ladder("codex_cli", both), ["aether_agent", ""])
        self.assertEqual(self.r.ladder("", lambda p: p == "codex_cli"), [""])
        secs = self.r.rest("aether_agent", RuntimeError("429: kullanım sınırı"))
        self.assertEqual(secs, self.r.LIMIT_REST)
        self.assertEqual(self.r.ladder("", both), [""])
        with mock.patch.object(self.r.time, "time", return_value=time.time() + self.r.LIMIT_REST + 5):
            self.assertEqual(self.r.ladder("", both), ["aether_agent", ""])
        self.assertEqual(self.r.rest("openai_compat@nvidia", RuntimeError("401")),
                         self.r.DOWN_REST)

    def test_what_counts_as_switchable(self):
        self.assertTrue(self.r.should_switch(RuntimeError("429 Too Many Requests")))
        self.assertTrue(self.r.should_switch(RuntimeError("Claude Code oturumu kapalı.")))
        self.assertFalse(self.r.should_switch(RuntimeError("SyntaxError in your request")))

    def test_dev_agent_uses_gemini_when_nvidia_unavailable(self):
        from actions import dev_agent
        from core import nvidia_account
        model = mock.Mock(text="Gemini yanıtı")
        with mock.patch.object(self.r, "ladder", return_value=["aether_agent", ""]), \
             mock.patch.object(nvidia_account, "api_key", return_value=""), \
             mock.patch.object(dev_agent.gemini, "call", return_value=model) as gem:
            self.assertEqual(dev_agent._get_model().generate_content("kod").text,
                             "Gemini yanıtı")
        gem.assert_called_once()

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


class OpusFirstTest(unittest.TestCase):
    def test_opus_first_with_sonnet_fallback(self):
        from core import agent_coding
        with mock.patch("memory.config_manager.get_plugin_config", return_value={}):
            self.assertEqual(agent_coding.claude_models(), ["opus", "sonnet"])
        cmd = agent_coding._claude_cmd("claude", "opus")
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
        self.assertEqual(cmd[cmd.index("--fallback-model") + 1], "sonnet")
        self.assertIn("WebSearch", cmd[cmd.index("--allowedTools") + 1])
        self.assertNotIn("--fallback-model", agent_coding._claude_cmd("claude", "sonnet"))

    def test_refused_model_steps_down(self):
        from core import agent_coding
        tried = []

        def once(exe, model, folder, prompt, log):
            tried.append(model)
            if model == "opus":
                return "", 1, ["Error: model not available on your plan"], ""
            return "Tamamlandı.", 0, [], ""
        with mock.patch("core.claude_coding._executable", return_value="claude"), \
             mock.patch("memory.config_manager.get_plugin_config", return_value={}), \
             mock.patch.object(agent_coding, "_claude_once", side_effect=once):
            self.assertEqual(agent_coding._run_claude(Path("."), "p", lambda m: None), "Tamamlandı.")
        self.assertEqual(tried, ["opus", "sonnet"])

    def test_brief_asks_for_complete_verified_work(self):
        from core import agent_coding
        b = agent_coding._brief("bir site yap", "", "")
        self.assertIn("No placeholders", b)
        self.assertIn("think hard", b)

    def test_setup_plugin_reports_and_saves_nvidia_model(self):
        from plugins import coding_setup
        from core import nvidia_account
        with mock.patch.object(nvidia_account, "status_text",
                               return_value="NVIDIA erişimi doğrulandı."):
            self.assertIn("NVIDIA erişimi doğrulandı.",
                          coding_setup.run({"action": "status"}))
        saved = {}
        with mock.patch.object(nvidia_account, "available_models",
                               return_value=["nvidia/nemotron-3.5-lightning-30b-a3b"]), \
             mock.patch("memory.config_manager.save_plugin_config",
                        side_effect=lambda ns, v: saved.update({ns: v})):
            coding_setup.run({
                "action": "model", "name": "nvidia/nemotron-3.5-lightning-30b-a3b"})
        self.assertEqual(saved["coding"]["nvidia_models"],
                         ["nvidia/nemotron-3.5-lightning-30b-a3b"])
