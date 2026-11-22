"""AETHER Türkçe masaüstü arayüzü ve pano hızlı işlemleri."""

import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TurkishInterfaceTests(unittest.TestCase):
    def test_changed_gui_modules_parse(self):
        for path in (
            "gui/overlays.py", "gui/providers_panel.py", "gui/window.py",
            "gui/widgets.py", "gui/control_center.py", "gui/chess_panel.py",
            "gui/scan_panel.py", "gui/prototype_panel.py", "gui/location_map.py",
        ):
            with self.subTest(path=path):
                ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

    def test_visible_controls_use_turkish(self):
        overlay = (ROOT / "gui/overlays.py").read_text(encoding="utf-8")
        window = (ROOT / "gui/window.py").read_text(encoding="utf-8")
        providers = (ROOT / "gui/providers_panel.py").read_text(encoding="utf-8")
        for text in (
            "PANODAKİ METİN ALGILANDI", '"ÇEVİR"', '"ÖZETLE"',
            '"AÇIKLA"', '"DÜZELT"', "GEMINI API ANAHTARI",
            "SES CİHAZLARI", "UZAKTAN ERİŞİM",
        ):
            with self.subTest(text=text):
                self.assertIn(text, overlay)
        for text in ("GÖREVLER", "RUTİNLER", "UYANDIRMA", "BASILI TUT KONUŞ"):
            with self.subTest(text=text):
                self.assertIn(text, window)
        for text in ("DİNLEME", "DÜŞÜNME", "KONUŞMA", "KAYDET VE UYGULA"):
            with self.subTest(text=text):
                self.assertIn(text, providers)

    def test_clipboard_buttons_execute_turkish_instructions(self):
        # Keep Qt in its own process; the other UI tests require one QApplication.
        script = r'''
from PyQt6.QtWidgets import QApplication, QPushButton, QLabel
from gui.overlays import ClipboardPanel
app = QApplication.instance() or QApplication([])
panel = ClipboardPanel()
buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
assert {'ÇEVİR', 'ÖZETLE', 'AÇIKLA', 'DÜZELT'} <= set(buttons), buttons
assert any('PANODAKİ METİN ALGILANDI' in l.text() for l in panel.findChildren(QLabel))
messages = []
panel.action_requested.connect(messages.append)
for label in ('ÇEVİR', 'ÖZETLE', 'AÇIKLA', 'DÜZELT'):
    panel.show_clipboard('Hello world from AETHER')
    buttons[label].click()
    assert messages and 'Hello world from AETHER' in messages[-1], label
    assert any(x in messages[-1] for x in ('Türkçeye', 'Türkçe', 'dil bilgisi')), messages[-1]
assert 'İngilizceye çevir' not in messages[0]
panel.close()
'''
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
