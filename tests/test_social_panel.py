import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QUrl

from gui import social_panel


class RedirectTests(unittest.TestCase):
    def test_chatgpt_accepts_named_openai_auth_hosts_only_over_https(self):
        for host in ("chat.openai.com", "auth.openai.com", "auth0.openai.com",
                     "setup.auth.openai.com"):
            with self.subTest(host=host):
                self.assertTrue(social_panel.permitted_url(QUrl(f"https://{host}/"), "chatgpt"))
                self.assertFalse(social_panel.permitted_url(QUrl(f"https://{host}/"), "claude"))
        for address in ("http://auth.openai.com", "https://auth0.openai.com:9443",
                        "https://auth.openai.com.example.org", "https://accounts.google.com",
                        "https://example@auth0.openai.com"):
            with self.subTest(address=address):
                self.assertFalse(social_panel.permitted_url(QUrl(address), "chatgpt"))

    def test_chatgpt_login_uses_the_current_embedded_view(self):
        view = Mock()
        panel = Mock(_site="chatgpt", _views={"chatgpt": [view, ""]})
        social_panel.SocialPanel._open_chatgpt_login(panel)
        view.setUrl.assert_called_once_with(QUrl("https://chatgpt.com/auth/login"))
        self.assertIsNone(panel._draft_request)


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


class GoogleSignInTests(unittest.TestCase):
    def test_external_sign_in_starts_on_chatgpt_without_reusing_redirect(self):
        with patch.object(social_panel.QDesktopServices, "openUrl", return_value=True) as launch:
            self.assertTrue(social_panel.open_in_browser("chatgpt", login=True))
        launch.assert_called_once_with(QUrl("https://chatgpt.com/auth/login"))

    def test_google_handoff_cancels_embedded_draft(self):
        panel = Mock(_blocked=set(), _draft_request=object())
        social_panel.SocialPanel._navigation_blocked(panel, "chatgpt", "accounts.google.com")
        self.assertTrue(panel._chatgpt_google_blocked)
        self.assertIsNone(panel._draft_request)
        self.assertIn("ayrı tarayıcıda", panel._set_status.call_args.args[1])


class GitHubRoutingTests(unittest.TestCase):
    def test_github_website_uses_system_browser_without_embedded_webengine(self):
        from gui.window import MainWindow

        owner = Mock()
        with patch.object(social_panel, "open_in_browser", return_value=True) as launch, patch.object(
            social_panel, "SocialPanel"
        ) as embedded:
            MainWindow._open_social(owner, "github")
        launch.assert_called_once_with("github")
        embedded.assert_not_called()
        owner._log.append_log.assert_not_called()

    def test_browser_launch_error_is_reported_instead_of_escaping_qt_slot(self):
        from gui.window import MainWindow

        owner = Mock()
        with patch.object(social_panel, "open_in_browser", side_effect=RuntimeError):
            MainWindow._open_social(owner, "github")
        self.assertIn("https://github.com/", owner._log.append_log.call_args.args[0])


class TikTokPlaybackTests(unittest.TestCase):
    def test_browser_handoff_preserves_public_video_without_parameters(self):
        page = QUrl("https://www.tiktok.com/@example/video/123?tracking=x#fragment")
        with patch.object(social_panel.QDesktopServices, "openUrl", return_value=True) as launch:
            self.assertTrue(social_panel.open_in_browser("tiktok", page_url=page))
        launch.assert_called_once_with(QUrl("https://www.tiktok.com/@example/video/123"))

    def test_browser_handoff_does_not_forward_login_or_other_origins(self):
        for url in ("https://www.tiktok.com/login?code=x",
                    "https://www.tiktok.com.example.org/@example/video/123"):
            with self.subTest(url=url):
                self.assertEqual(social_panel.browser_address("tiktok", page_url=QUrl(url)),
                                 "https://www.tiktok.com/")
