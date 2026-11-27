"""A slow tool never holds the conversation; its result arrives later."""
import asyncio
import threading
import time
import unittest
from pathlib import Path

from core import toolwait


class ToolWait(unittest.TestCase):
    def test_fast_tool_returns_its_result(self):
        self.assertEqual(asyncio.run(toolwait.run("x", lambda: "tamam", wait=2)), "tamam")

    def test_slow_tool_lets_go_and_reports_later(self):
        late, got = [], threading.Event()

        def slow():
            time.sleep(0.6)
            return "rapor hazır"

        def on_late(name, text):
            late.append((name, text))
            got.set()

        async def main():
            t0 = time.monotonic()
            out = await toolwait.run("research", slow, wait=0.2, on_late=on_late)
            took = time.monotonic() - t0
            await asyncio.sleep(0.8)                      # the loop keeps running meanwhile
            return out, took
        out, took = asyncio.run(main())
        self.assertIn("STILL RUNNING", out)
        self.assertLess(took, 0.5)
        self.assertTrue(got.wait(2))
        self.assertEqual(late, [("research", "rapor hazır")])

    def test_slow_tool_failure_is_reported_too(self):
        late = []

        def boom():
            time.sleep(0.3)
            raise RuntimeError("ağ yok")

        async def main():
            out = await toolwait.run("x", boom, wait=0.1, on_late=lambda n, t: late.append(t))
            await asyncio.sleep(0.5)
            return out
        self.assertIn("STILL RUNNING", asyncio.run(main()))
        self.assertEqual(late, ["failed: ağ yok"])

    def test_main_uses_it_and_handles_go_away(self):
        src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("r = await self._run_blocking(name, lambda: self._action_registry.run(name, args, _ctx))", src)
        self.assertIn("self._plugin_registry.run(name, args, player=self.ui, session_memory=None))", src)
        self.assertIn('getattr(response, "go_away", None)', src)
        self.assertIn('self.request_reconnect(keep_context=True, reason="go_away")', src)
        self.assertIn("self._outbox.append(text)", src)              # typed while offline: kept
        self.assertIn("self._outbox.append(instruction)", src)       # a late tool report while offline: kept
        self.assertIn("tg.create_task(self._flush_outbox())", src)


if __name__ == "__main__":
    unittest.main()


class MultiStep(unittest.TestCase):
    def test_background_results_continue_the_users_plan(self):
        root = __import__("pathlib").Path(__file__).resolve().parent.parent
        prompt = (root / "core" / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("[MULTI-STEP REQUESTS]", prompt)
        self.assertIn("go straight to the next step", prompt)
        main = (root / "main.py").read_text(encoding="utf-8")
        self.assertIn("{self._CONTINUE} Result: {text}", main)
        blender = (root / "plugins" / "blender_studio.py").read_text(encoding="utf-8")
        self.assertNotIn("Yeni bir işlem başlatma", blender)
        self.assertIn("şimdi sıradakine geç", blender)
