"""A tool that fails for a missing library: Mayk may offer to install it — only its own dependencies."""
import unittest
from pathlib import Path
from unittest.mock import patch

from core import installer
from plugins import install_package


class MissingPackage(unittest.TestCase):
    def test_own_dependency_is_offered(self):
        msg = "status=failed action=send_message PyAutoGUI is not installed - run: pip install pyautogui"
        self.assertEqual(installer.missing_package(msg), "pyautogui")
        self.assertEqual(installer.missing_package("Run: pip install send2trash — then retry"), "send2trash")

    def test_foreign_package_is_never_offered(self):
        self.assertEqual(installer.missing_package("pip install evil-package-xyz"), "")
        ok, msg = installer.install("evil-package-xyz")
        self.assertFalse(ok)
        self.assertIn("güvenlik", msg)

    def test_plugin_installs_after_yes(self):
        with patch.object(installer, "_pip", return_value=True) as pip:
            out = install_package.run({"package": "pyautogui"})
        pip.assert_called_once()
        self.assertIn("kuruldu", out)

    def test_main_adds_the_offer(self):
        src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("pkg = installer.missing_package(result)", src)
        self.assertIn("[MISSING_PACKAGE]", src)
        self.assertIn('self.ui.write_log("SYS: ✅ Hoparlör yeniden bağlandı.")', src)


if __name__ == "__main__":
    unittest.main()
