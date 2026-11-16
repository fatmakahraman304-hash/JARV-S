import threading
import unittest

from core import activity


class ActivityTests(unittest.TestCase):
    def test_tools_map_to_nodes(self):
        self.assertEqual(activity.node_for_tool("web_search"), "web")
        self.assertEqual(activity.node_for_tool("youtube_video"), "youtube")
        self.assertEqual(activity.node_for_tool("send_message", {"platform": "WhatsApp"}), "whatsapp")
        self.assertEqual(activity.node_for_tool("send_message", {"platform": "insta"}), "instagram")
        self.assertEqual(activity.node_for_tool("send_message", {"platform": "Discord"}), "messages")
        self.assertEqual(activity.node_for_tool("some_new_plugin"), "tasks")
        for key in activity._TOOL_NODE.values():
            self.assertIn(key, activity.NODE_LABEL)

    def test_outcome_status_is_respected(self):
        self.assertEqual(activity.status_of("status=done action=x"), "ok")
        self.assertEqual(activity.status_of("status=failed action=x reason=y"), "fail")
        self.assertEqual(activity.status_of("status=unverified action=x reason=y"), "warn")
        self.assertEqual(activity.status_of("Error: boom"), "fail")

    def test_record_tool_counts_and_reports_failures_honestly(self):
        before = activity.counts().get("computer", 0)
        activity.record_tool("open_app", {"app_name": "Spotify"}, "status=failed action=open_app reason=no")
        last = activity.recent(1)[0]
        self.assertEqual(last.node, "computer")
        self.assertEqual(last.status, "fail")
        self.assertIn("Spotify", last.text)
        self.assertEqual(activity.counts()["computer"], before + 1)
        activity.record_tool("web_search", {"query": "q"}, error=RuntimeError("x"))
        self.assertEqual(activity.recent(1)[0].status, "fail")

    def test_since_and_thread_safety(self):
        start = activity.last_seq()

        def burst():
            for _ in range(50):
                activity.record("web", "x")

        threads = [threading.Thread(target=burst) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(activity.last_seq(), start + 200)
        self.assertTrue(all(e.seq > start for e in activity.since(start)))

    def test_record_never_raises(self):
        activity.record("not-a-node", None, "ok")
        self.assertEqual(activity.recent(1)[0].node, "tasks")


class ControlCenterPluginTests(unittest.TestCase):
    def test_plugin_opens_through_player_and_summarises(self):
        from plugins import control_center

        calls = []

        class Player:
            def show_control_center(self, opened=True):
                calls.append(opened)

        self.assertIn("status=done", control_center.run({}, player=Player()))
        self.assertIn("status=done", control_center.run({"action": "close"}, player=Player()))
        self.assertEqual(calls, [True, False])
        self.assertIn("status=failed", control_center.run({}, player=None))
        activity.record_tool("weather_report", {}, "sunny")
        self.assertIn("Hava", control_center.run({"action": "summary"}))


if __name__ == "__main__":
    unittest.main()
