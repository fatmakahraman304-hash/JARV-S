import unittest
from unittest.mock import Mock, patch

from gui import social_panel


class BrowserLaunchTests(unittest.TestCase):
    def test_windows_falls_back_to_edge_if_default_launch_fails(self):
        with patch.object(social_panel.sys, "platform", "win32"), patch.object(
            social_panel.QDesktopServices, "openUrl", return_value=False
        ), patch.object(social_panel.os, "startfile", create=True) as start:
            self.assertTrue(social_panel.open_in_browser("chatgpt"))
            start.assert_called_once_with("microsoft-edge:https://chatgpt.com/")

    def test_explicit_edge_skips_default_handler_and_reports_failure(self):
        with patch.object(social_panel.sys, "platform", "win32"), patch.object(
            social_panel.QDesktopServices, "openUrl"
        ) as default, patch.object(social_panel.os, "startfile", create=True, side_effect=OSError):
            self.assertFalse(social_panel.open_in_browser("claude", edge=True))
            default.assert_not_called()


@unittest.skipIf(social_panel.QWebEngineView is None, "WebEngine required")
class LoadFailureTests(unittest.TestCase):
    def test_failed_load_keeps_error_code(self):
        info = Mock()
        info.status.return_value = social_panel.QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus
        info.errorDomain.return_value = social_panel.QWebEngineLoadingInfo.ErrorDomain.DnsErrorDomain
        info.errorCode.return_value = -105
        panel = Mock(_failed=set(), _blocked=set())
        social_panel.SocialPanel._loading_changed(panel, "chatgpt", info)
        self.assertIn("chatgpt", panel._failed)
        self.assertIn("DNS", panel._set_status.call_args.args[1])
        self.assertIn("-105", panel._set_status.call_args.args[1])

    def test_load_failure_preserves_blocked_redirect_message(self):
        info = Mock()
        info.status.return_value = social_panel.QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus
        panel = Mock(_failed=set(), _blocked={"chatgpt"}, _views={"chatgpt": [None, "blocked redirect"]})
        social_panel.SocialPanel._loading_changed(panel, "chatgpt", info)
        panel._set_status.assert_called_once_with("chatgpt", "blocked redirect")
