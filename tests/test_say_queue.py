"""Volunteered sentences never cut into a reply: queued, sent one at a time at calm moments."""
import asyncio
import threading
import time
import types
import unittest
from collections import deque
from unittest import mock


def _main():
    from tests._main_import import load_main
    return load_main()


class SayQueueTest(unittest.TestCase):
    def make(self, main, speaking=False, last_user=-100.0):
        sent = []

        class Session:
            async def send_client_content(self, turns, turn_complete):
                sent.append(turns["parts"][0]["text"])

        fake = types.SimpleNamespace(
            _say_queue=deque(), _last_said_at=float("-inf"), _is_speaking=speaking,
            _speaking_lock=threading.Lock(), audio_in_queue=None, session=Session(),
            _last_user_speech=time.monotonic() + last_user, _outbox=[],
            _SAY_GAP=0.3, _SAY_CALM=main.MaykLive._SAY_CALM, _SAY_MAX_WAIT=60.0)
        fake._calm_for_say = lambda now: main.MaykLive._calm_for_say(fake, now)
        return fake, sent

    def run_drain(self, main, fake, seconds):
        async def go():
            task = asyncio.create_task(main.MaykLive._drain_say(fake))
            await asyncio.sleep(seconds)
            task.cancel()
        asyncio.run(go())

    def test_waits_while_speaking(self):
        main = _main()
        fake, sent = self.make(main, speaking=True)
        fake._say_queue.append((time.monotonic(), "a"))
        self.run_drain(main, fake, 1.0)
        self.assertEqual(sent, [])

    def test_sends_one_at_a_time_spaced(self):
        main = _main()
        fake, sent = self.make(main)
        fake._say_queue.extend([(time.monotonic(), "a"), (time.monotonic(), "b")])
        self.run_drain(main, fake, 0.6)
        self.assertEqual(sent, ["a"])                       # the gap holds the second one back
        self.run_drain(main, fake, 0.9)
        self.assertEqual(sent, ["a", "b"])

    def test_said_anyway_after_max_wait(self):
        main = _main()
        fake, sent = self.make(main, speaking=True)
        fake._say_queue.append((time.monotonic() - 61, "late"))
        self.run_drain(main, fake, 0.8)
        self.assertEqual(sent, ["late"])

    def test_waits_for_user_to_finish(self):
        main = _main()
        fake, sent = self.make(main, last_user=0.0)         # user spoke just now
        fake._say_queue.append((time.monotonic(), "a"))
        self.run_drain(main, fake, 0.8)
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
