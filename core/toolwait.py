"""Run a blocking tool without letting it hold the conversation hostage.

`await run(name, fn, wait, on_late)` returns the tool's result if it finishes
within `wait` seconds. Otherwise the tool keeps running in its thread, a
STILL RUNNING note is returned at once (so AETHER can speak and listen again),
and `on_late(name, result_text)` is called when it does finish.
"""
from __future__ import annotations

import asyncio

DEFAULT = 45.0
WAITS = {"install_package": 240.0, "dev_agent": 90.0, "web_search": 60.0, "application_learning": 90.0, "browser_control": 75.0}


def still_running(name: str, wait: float) -> str:
    return (f"STILL RUNNING: '{name}' is taking longer than {wait:.0f} seconds and continues in the background. "
            "Tell the user so in one short sentence; its result will be reported automatically when it finishes. "
            "Do not call it again.")


async def run(name: str, fn, wait: float | None = None, on_late=None):
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(None, fn)
    wait = WAITS.get(name, DEFAULT) if wait is None else wait
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=wait)
    except asyncio.TimeoutError:
        def done(f):
            try:
                result = f.result()
            except BaseException as exc:
                result = f"failed: {exc}"
            if on_late is not None:
                on_late(name, str(result or "Done.")[:1500])
        fut.add_done_callback(done)
        return still_running(name, wait)
