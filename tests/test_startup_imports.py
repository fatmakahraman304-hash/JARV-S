"""The first window must not pay for an unused Gemini SDK."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StartupImports(unittest.TestCase):
    def execute(self, script, root=ROOT):
        environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        if root != ROOT:
            environment.update(LOCALAPPDATA=str(root / "LocalAppData"),
                               APPDATA=str(root / "AppData"), XDG_DATA_HOME=str(root / "Data"))
        result = subprocess.run([sys.executable, "-c", script], cwd=root,
                                env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_import_main_does_not_execute_google_sdk(self):
        self.execute('''
import importlib.abc, sys, types
class NoSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'google.genai' or fullname.startswith('google.genai.'):
            raise AssertionError('Gemini SDK loaded before it was needed')
sys.meta_path.insert(0, NoSDK())
sys.modules['sounddevice'] = types.ModuleType('sounddevice')
import main
assert not any(n == 'google.genai' or n.startswith('google.genai.') for n in sys.modules)
assert main._pcm_level(main.np.zeros(160, dtype=main.np.int16)) == 0.
assert main.AetherLive._build_config.__annotations__['return'] == 'types.LiveConnectConfig'
''')

    def test_first_type_access_loads_real_sdk_and_preserves_response_shape(self):
        self.execute('''
import sys, types
sys.modules['sounddevice'] = types.ModuleType('sounddevice')
import main
assert 'google.genai' not in sys.modules
response = main.types.FunctionResponse(name='offline_probe', response={'result':'unverified'})
assert 'google.genai.types' in sys.modules
assert response.name == 'offline_probe'
assert response.response == {'result':'unverified'}
from google.genai import types as real_types
assert isinstance(response, real_types.FunctionResponse)
assert callable(main.genai.Client)
''')


    def test_first_setup_window_opens_with_sdk_import_blocked(self):
        from tools.measure_window_startup import source_copy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_copy(ROOT, root)
            self.execute('''
import importlib.abc, sys, types
class NoSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'google.genai' or fullname.startswith('google.genai.'):
            raise AssertionError('First setup window must not execute the SDK')
sys.meta_path.insert(0, NoSDK())
sys.modules['sounddevice'] = types.ModuleType('sounddevice')
import main
ui = main.AetherUI('')
ui._app.processEvents()
assert ui._win.isVisible()
assert 'google.genai' not in sys.modules
ui._win.close()
ui._app.processEvents()
''', root)


class StartupSourcePrivacy(unittest.TestCase):
    def test_clean_source_copy_excludes_keys_memory_and_signing_files(self):
        from tools.measure_window_startup import source_copy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            root.mkdir()
            target = Path(directory) / "copy"
            target.mkdir()
            contents = {"main.py":"print('code')", "requirements.txt":"existing-dependency",
                        "config/api_keys.json":"synthetic-private", "config/private.py":"private = True",
                        "memory/long_term.json":"synthetic-history", "android/key.jks":"synthetic-key"}
            for name, content in contents.items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "add", "--", *contents], cwd=root, check=True)
            source_copy(root, target)
            self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()},
                             {"main.py", "requirements.txt"})
