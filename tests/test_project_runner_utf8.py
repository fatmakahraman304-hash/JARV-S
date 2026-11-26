"""Windows'ta FRIDAY kod ajanı çalıştırma çıktısı UTF-8 ve gerçek çıkış kodu."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import dev_agent


class ProjectRunnerUtf8Tests(unittest.TestCase):
    def test_python_turkish_output_survives_windows_codepage(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "main.py").write_text(
                'print("Kullanım: python main.py <sayı1> <sayı2> <işlem>")\n'
                'print("İşlemler: toplama, çıkarma, bölme, çarpma")\n',
                encoding="utf-8",
            )
            # Windows'taki eski terminal kod sayfasını taklit et.
            with mock.patch.dict(os.environ, {"PYTHONIOENCODING": "cp1252"}):
                result = dev_agent._run_project("python main.py", folder)
        self.assertIn("BAŞARILI (çıkış kodu: 0)", result)
        self.assertIn("Kullanım:", result)
        self.assertIn("<sayı1> <sayı2> <işlem>", result)
        self.assertIn("İşlemler: toplama, çıkarma, bölme, çarpma", result)
        self.assertNotIn("\ufffd", result)

    def test_nonzero_exit_code_is_reported_as_failure_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "main.py").write_text(
                'import sys\n'
                'print("Kullanım hatası: eksik işlem")\n'
                'sys.exit(2)\n',
                encoding="utf-8",
            )
            result = dev_agent._run_project("python main.py", folder)
        self.assertIn("BAŞARISIZ (çıkış kodu: 2)", result)
        self.assertIn("Kullanım hatası", result)
        self.assertNotIn("\ufffd", result)

    def test_python_process_receives_utf8_flags(self):
        with mock.patch.object(dev_agent.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "tamam"
            run.return_value.stderr = ""
            dev_agent._run_project("python main.py", Path("."))
        self.assertEqual(run.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(run.call_args.kwargs["env"]["PYTHONUTF8"], "1")
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.args[0][0], sys.executable)


if __name__ == "__main__":
    unittest.main()
