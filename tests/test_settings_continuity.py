"""Run Qt in its own process so other UI tests retain their single QApplication."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SettingsIntegrationTests(unittest.TestCase):
    def test_application_form_dispatches_and_history_opens(self):
        script = r'''
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QLineEdit, QCheckBox
from gui.settings_page import SettingsPage
app = QApplication.instance() or QApplication([])
class Owner(QWidget):
    def __getattr__(self, name):
        if name == '_build_update_button': return lambda: QPushButton('Güncelle')
        if name == '_wake_state': return lambda: {}
        if name.startswith('_'): return lambda *args: False
        raise AttributeError(name)
owner = Owner()
owner._application_player = Mock()
with patch('core.application_learning.report', return_value='CapCut — durduruldu'):
    dialog = SettingsPage(owner)
    assert dialog.show_category('Uygulamalar')
    fields = {w.accessibleName():w for w in dialog.findChildren(QLineEdit)}
    fields['Uygulama adı'].setText('CapCut')
    fields['İstenen uygulama işlemleri'].setText('Videoyu kırp')
    with patch('plugins.application_learning.run', return_value='Başlatıldı') as run:
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Araştır, geliştir ve test et').click()
        args = run.call_args.args[0]
        assert args['name']=='CapCut' and args['goal']=='Videoyu kırp' and args['publish'] is True
    dialog.show_category('Zekâ ve hafıza')
    with patch('memory.continuity.resume_text', return_value='Son görev'):
        next(b for b in dialog.findChildren(QPushButton) if b.accessibleName()=='Nerede kaldık').click()
    owner._application_player.show_content.assert_called_with('Nerede kaldık', 'Son görev')
    dialog.close()
'''
        with tempfile.TemporaryDirectory() as temp:
            env=dict(os.environ, QT_QPA_PLATFORM='offscreen', LOCALAPPDATA=temp, XDG_DATA_HOME=temp)
            result=subprocess.run([sys.executable,'-c',script], cwd=Path(__file__).resolve().parents[1],
                                  env=env, capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__ == '__main__': unittest.main()
