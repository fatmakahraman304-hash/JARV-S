import subprocess
import unittest
from unittest.mock import Mock, patch

from core import tiktok_app
from core.social_sites import site_for_command


class TikTokAppTests(unittest.TestCase):
    def test_launches_the_registered_app(self):
        app_id = "TikTokPackage_example!App"
        result = subprocess.CompletedProcess([], 0, stdout=f"{app_id}\r\n".encode("ascii"))
        with patch.object(tiktok_app.sys, "platform", "win32"), patch.object(
            tiktok_app.subprocess, "run", return_value=result
        ) as lookup, patch.object(tiktok_app.os, "startfile", create=True) as start:
            self.assertIn("Windows’a iletildi", tiktok_app.launch_tiktok())
        self.assertIn("Get-StartApps -Name 'TikTok'", lookup.call_args.args[0][-1])
        start.assert_called_once_with("shell:AppsFolder\\" + app_id)

    def test_missing_app_prompts_for_installation(self):
        result = subprocess.CompletedProcess([], 0, stdout=b"")
        with patch.object(tiktok_app.sys, "platform", "win32"), patch.object(
            tiktok_app.subprocess, "run", return_value=result
        ), patch.object(tiktok_app.os, "startfile", create=True) as start:
            self.assertIn("Microsoft Store", tiktok_app.launch_tiktok())
        start.assert_not_called()

    def test_launch_failure_is_reported(self):
        result = subprocess.CompletedProcess([], 0, stdout=b"TikTokPackage_example!App")
        with patch.object(tiktok_app.sys, "platform", "win32"), patch.object(
            tiktok_app.subprocess, "run", return_value=result
        ), patch.object(tiktok_app.os, "startfile", create=True, side_effect=OSError):
            self.assertIn("TikTok başlatılamadı", tiktok_app.launch_tiktok())

    def test_tiktok_command_opens_the_app_without_switching_the_hud(self):
        from gui.window import MainWindow

        owner = Mock()
        site = site_for_command("JARVIS, TikTok’u aç.")
        MainWindow._open_social(owner, site)
        owner._open_tiktok_app.assert_called_once_with()
        owner._hud_cam_stack.setCurrentWidget.assert_not_called()
