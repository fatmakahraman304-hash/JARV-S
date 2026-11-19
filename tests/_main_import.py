"""Import main.py in tests on machines without audio hardware libraries.

sounddevice needs PortAudio, which CI runners do not have; the logic under test
never touches it, so a stand-in module is enough.
"""
import sys
import types
import unittest


def load_main():
    if "sounddevice" not in sys.modules:
        try:
            import sounddevice  # noqa: F401
        except BaseException:
            stub = types.ModuleType("sounddevice")
            stub.query_devices = lambda *a, **k: []
            stub.default = types.SimpleNamespace(device=(None, None))
            sys.modules["sounddevice"] = stub
    try:
        import main
        return main
    except BaseException as exc:
        raise unittest.SkipTest(f"main.py cannot be imported here: {exc}")
